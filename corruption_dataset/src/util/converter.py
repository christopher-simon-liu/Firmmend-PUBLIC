"""
Hex/ELF to binary converter.

Converts various firmware formats to binary dumps that simulate
what would be read from target flash memory.
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from intelhex import IntelHex
from elftools.elf.elffile import ELFFile

logger = logging.getLogger(__name__)

# Common STM32 flash configurations
FLASH_CONFIGS = {
    # P2IM
    'STM32F429ZI': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB https://www.st.com/en/microcontrollers-microprocessors/stm32f429zi.html https://www.st.com/resource/en/reference_manual/dm00031020-stm32f405-415-stm32f407-417-stm32f427-437-and-stm32f429-439-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf
    'STM32F103RB': {'start': 0x08000000, 'size': 128 * 1024},    # 128KB https://www.st.com/en/microcontrollers-microprocessors/stm32f103rb.html https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
    'SAM3X8E': {'start': 0x00000000, 'size': 512 * 1024},    # 512KB https://www.microchip.com/en-us/product/ATSAM3X8E https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-11057-32-bit-Cortex-M3-Microcontroller-SAM3X-SAM3A_Datasheet.pdf
    'MK64FN1M0VLL12': {'start': 0x00000000, 'size': 1024 * 1024},  # 1MB https://www.nxp.com/part/MK64FN1M0VLL12 https://www.mouser.com/datasheet/2/813/K64P144M120SF5RM-1074828.pdf

    # STM32F4 series
    'STM32F405': {'start': 0x08000000, 'size': 1024 * 1024},   # 1MB
    'STM32F412': {'start': 0x08000000, 'size': 512 * 1024},    # 512KB
    'STM32F427': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB
    'STM32F446': {'start': 0x08000000, 'size': 512 * 1024},    # 512KB

    # STM32F7 series
    'STM32F745': {'start': 0x08000000, 'size': 1024 * 1024},   # 1MB
    'STM32F765': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB
    'STM32F777': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB

    # STM32H7 series
    'STM32H743': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB
    'STM32H750': {'start': 0x08000000, 'size': 128 * 1024},    # 128KB internal
    'STM32H753': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB
    'STM32H755': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB
    'STM32H757': {'start': 0x08000000, 'size': 2 * 1024 * 1024},  # 2MB

    # NXP automotive MCUs
    'S32K146': {'start': 0x00000000, 'size': 1024 * 1024},   # 1MB P-Flash
    'S32K344': {'start': 0x00000000, 'size': 4 * 1024 * 1024},  # 4MB code flash

    # AVR tinyAVR parts
    'ATTINY10': {'start': 0x00000000, 'size': 1024},         # 1KB flash
    'ATTINY3226': {'start': 0x00000000, 'size': 32 * 1024},  # 32KB flash

    # Default fallback
    'default': {'start': 0x08000000, 'size': 2 * 1024 * 1024},
}

# Typical bootloader size (16KB or 32KB for most boards)
DEFAULT_BOOTLOADER_SIZE = 16 * 1024


@dataclass
class ConversionResult:
    """Result of a firmware conversion."""
    success: bool
    output_path: Path | None
    flash_start: int
    flash_size: int
    data_start: int  # Where actual data begins
    data_size: int   # Size of actual data
    data_end: int    # Exclusive end address of meaningful placed data
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class BinaryConverter:
    """Converts firmware files to binary dumps."""

    def __init__(self, objcopy_path: str = None):
        """
        Initialize the converter.

        Args:
            objcopy_path: Path to objcopy binary (auto-detected if None)
        """
        self.objcopy_path = objcopy_path or self._find_objcopy()

    def _find_objcopy(self) -> str | None:
        """Find objcopy binary in PATH."""
        # Try common names
        for name in ['arm-none-eabi-objcopy', 'objcopy']:
            path = shutil.which(name)
            if path:
                logger.debug(f"Found objcopy: {path}")
                return path

        logger.warning("objcopy not found in PATH")
        return None

    def get_flash_config(self, chip_part: str) -> dict:
        """Get flash configuration for a chip part number."""
        # Try exact match first
        if chip_part in FLASH_CONFIGS:
            return FLASH_CONFIGS[chip_part]

        # Try prefix match (e.g., STM32F427VIT6 -> STM32F427)
        for prefix, config in FLASH_CONFIGS.items():
            if chip_part.upper().startswith(prefix.upper()):
                return config

        return FLASH_CONFIGS['default']

    def has_explicit_flash_config(self, chip_part: str | None) -> bool:
        """Return True when the chip part maps to a non-default flash config."""
        if not chip_part:
            return False
        if chip_part in FLASH_CONFIGS and chip_part != 'default':
            return True
        return any(
            prefix != 'default' and chip_part.upper().startswith(prefix.upper())
            for prefix in FLASH_CONFIGS
        )

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        chip_part: str = None,
        flash_start: int = None,
        flash_size: int = None,
        fill_value: int = 0xFF
    ) -> ConversionResult:
        """
        Convert a firmware file to binary.

        Args:
            input_path: Path to input file (hex, elf, apj, bin)
            output_path: Path for output binary
            chip_part: Chip part number for flash config
            flash_start: Override flash start address
            flash_size: Override flash size
            fill_value: Value to fill empty regions (0xFF = erased flash)

        Returns:
            ConversionResult with conversion details
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # Determine flash config
        if chip_part:
            config = self.get_flash_config(chip_part)
        else:
            config = FLASH_CONFIGS['default']

        if flash_start is None:
            flash_start = config['start']
        if flash_size is None:
            flash_size = config['size']

        # Determine file type and convert
        suffix = input_path.suffix.lower()

        try:
            if suffix == '.hex':
                return self._convert_hex(
                    input_path, output_path,
                    flash_start, flash_size, fill_value
                )
            elif suffix == '.elf':
                return self._convert_elf(
                    input_path, output_path,
                    flash_start, flash_size, fill_value
                )
            elif suffix == '.apj':
                return self._convert_apj(
                    input_path, output_path,
                    flash_start, flash_size, fill_value
                )
            elif suffix == '.bin':
                return self._copy_bin(
                    input_path, output_path,
                    flash_start, flash_size, fill_value
                )
            else:
                return ConversionResult(
                    success=False,
                    output_path=None,
                    flash_start=flash_start,
                    flash_size=flash_size,
                    data_start=0,
                    data_size=0,
                    data_end=0,
                    error=f"Unsupported file type: {suffix}"
                )
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=0,
                data_size=0,
                data_end=0,
                error=str(e)
            )

    def _convert_hex(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int
    ) -> ConversionResult:
        """Convert Intel HEX file to binary."""
        logger.info(f"Converting HEX: {input_path}")

        ih = IntelHex(str(input_path))

        # Get the actual data range
        if len(ih) == 0:
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=0,
                data_size=0,
                data_end=0,
                error="Empty HEX file"
            )

        data_start = ih.minaddr()
        data_end = ih.maxaddr()
        data_size = data_end - data_start + 1

        logger.debug(f"HEX data range: 0x{data_start:08X} - 0x{data_end:08X}")

        flash_end = flash_start + flash_size
        if data_end < flash_start or data_start >= flash_end:
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=data_start,
                data_size=data_size,
                data_end=data_start + data_size,
                error=(
                    "HEX data range does not overlap flash window: "
                    f"0x{data_start:08X}-0x{data_end:08X} vs "
                    f"0x{flash_start:08X}-0x{flash_end - 1:08X}"
                ),
            )

        # Create output binary
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write binary with padding
        ih.padding = fill_value
        ih.tobinfile(str(output_path), start=flash_start, size=flash_size)

        return ConversionResult(
            success=True,
            output_path=output_path,
            flash_start=flash_start,
            flash_size=flash_size,
            data_start=data_start,
            data_size=data_size,
            data_end=data_start + data_size,
        )

    def _convert_elf(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int
    ) -> ConversionResult:
        """Convert ELF file to binary."""
        logger.info(f"Converting ELF: {input_path}")

        # First, try using objcopy if available
        if self.objcopy_path:
            result = self._convert_elf_objcopy(
                input_path, output_path,
                flash_start, flash_size, fill_value
            )
            if result.success:
                return result
            logger.warning(f"objcopy failed, falling back to pyelftools: {result.error}")

        # Fall back to pyelftools
        return self._convert_elf_native(
            input_path, output_path,
            flash_start, flash_size, fill_value
        )

    def _convert_elf_objcopy(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int
    ) -> ConversionResult:
        """Convert ELF using objcopy."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use objcopy to create raw binary
        cmd = [
            self.objcopy_path,
            '-O', 'binary',
            '--gap-fill', f'0x{fill_value:02X}',
            str(input_path),
            str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                return ConversionResult(
                    success=False,
                    output_path=None,
                    flash_start=flash_start,
                    flash_size=flash_size,
                    data_start=0,
                    data_size=0,
                    data_end=0,
                    error=f"objcopy failed: {result.stderr}"
                )

            # Get actual data size
            data_size = output_path.stat().st_size

            # Pad to flash size if needed
            if data_size < flash_size:
                with open(output_path, 'ab') as f:
                    f.write(bytes([fill_value] * (flash_size - data_size)))

            return ConversionResult(
                success=True,
                output_path=output_path,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=flash_start,
                data_size=data_size,
                data_end=flash_start + data_size,
            )

        except subprocess.TimeoutExpired:
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=0,
                data_size=0,
                data_end=0,
                error="objcopy timed out"
            )

    def _convert_elf_native(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int
    ) -> ConversionResult:
        """Convert ELF using pyelftools (fallback)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize output buffer
        output_data = bytearray([fill_value] * flash_size)

        data_min = flash_start + flash_size
        data_max = flash_start

        copied_any = False

        with open(input_path, 'rb') as f:
            elf = ELFFile(f)

            for segment in elf.iter_segments():
                if segment['p_type'] != 'PT_LOAD':
                    continue

                seg_addr = segment['p_paddr']
                seg_size = segment['p_filesz']
                seg_data = segment.data()

                if seg_size == 0:
                    continue

                # Check if segment is in flash range
                if seg_addr < flash_start:
                    continue
                if seg_addr >= flash_start + flash_size:
                    continue

                # Calculate offset in output
                offset = seg_addr - flash_start

                # Copy data
                end_offset = min(offset + seg_size, flash_size)
                copy_size = end_offset - offset

                output_data[offset:offset + copy_size] = seg_data[:copy_size]
                copied_any = True

                # Track data range
                data_min = min(data_min, seg_addr)
                data_max = max(data_max, seg_addr + seg_size)

        if not copied_any:
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=0,
                data_size=0,
                data_end=0,
                error=(
                    "No loadable ELF segments overlap flash window: "
                    f"0x{flash_start:08X}-0x{flash_start + flash_size - 1:08X}"
                ),
            )

        # Write output
        with open(output_path, 'wb') as f:
            f.write(output_data)

        data_size = data_max - data_min if data_max > data_min else 0

        return ConversionResult(
            success=True,
            output_path=output_path,
            flash_start=flash_start,
            flash_size=flash_size,
            data_start=data_min,
            data_size=data_size,
            data_end=data_min + data_size if data_size > 0 else data_min,
        )

    def _convert_apj(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int
    ) -> ConversionResult:
        """Convert ArduPilot APJ file to binary."""
        logger.info(f"Converting APJ: {input_path}")

        # APJ is JSON with base64-encoded firmware
        import base64

        with open(input_path, 'r') as f:
            apj_data = json.load(f)

        if 'image' not in apj_data:
            return ConversionResult(
                success=False,
                output_path=None,
                flash_start=flash_start,
                flash_size=flash_size,
                data_start=0,
                data_size=0,
                data_end=0,
                error="APJ file missing 'image' field"
            )

        # Decode firmware image
        firmware_data = base64.b64decode(apj_data['image'])
        data_size = len(firmware_data)

        logger.debug(f"APJ firmware size: {data_size} bytes")

        # APJ contains application firmware (without bootloader)
        # Typically loaded at flash_start + bootloader_size
        app_offset = DEFAULT_BOOTLOADER_SIZE

        # Create output buffer
        output_data = bytearray([fill_value] * flash_size)

        # Copy firmware data at application offset
        end_offset = min(app_offset + data_size, flash_size)
        copy_size = end_offset - app_offset

        output_data[app_offset:app_offset + copy_size] = firmware_data[:copy_size]

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(output_data)

        return ConversionResult(
            success=True,
            output_path=output_path,
            flash_start=flash_start,
            flash_size=flash_size,
            data_start=flash_start + app_offset,
            data_size=data_size,
            data_end=flash_start + app_offset + copy_size,
        )

    def _copy_bin(
        self,
        input_path: Path,
        output_path: Path,
        flash_start: int,
        flash_size: int,
        fill_value: int,
    ) -> ConversionResult:
        """Copy binary file with padding to flash size."""
        logger.info(f"Copying BIN: {input_path}")

        data = input_path.read_bytes()
        data_size = len(data)

        # Pad to flash size
        if data_size < flash_size:
            data = data + bytes([fill_value] * (flash_size - data_size))
        elif data_size > flash_size:
            data = data[:flash_size]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)

        return ConversionResult(
            success=True,
            output_path=output_path,
            flash_start=flash_start,
            flash_size=flash_size,
            data_start=flash_start,
            data_size=min(data_size, flash_size),
            data_end=flash_start + min(data_size, flash_size),
        )

    def add_bootloader(
        self,
        binary_path: Path,
        bootloader_path: Path,
        bootloader_offset: int = 0
    ) -> bool:
        """
        Add bootloader to an existing binary.

        Args:
            binary_path: Path to the binary file to modify
            bootloader_path: Path to bootloader binary
            bootloader_offset: Offset where bootloader should be placed

        Returns:
            True if successful
        """
        if not bootloader_path.exists():
            logger.warning(f"Bootloader not found: {bootloader_path}")
            return False

        bootloader_data = bootloader_path.read_bytes()
        binary_data = bytearray(binary_path.read_bytes())

        # Insert bootloader
        end_offset = min(bootloader_offset + len(bootloader_data), len(binary_data))
        copy_size = end_offset - bootloader_offset

        binary_data[bootloader_offset:bootloader_offset + copy_size] = \
            bootloader_data[:copy_size]

        binary_path.write_bytes(binary_data)

        logger.info(f"Added bootloader ({len(bootloader_data)} bytes) at offset {bootloader_offset}")
        return True


def _parse_int_arg(value: str) -> int:
    """Parse integers in decimal or 0x-prefixed hexadecimal form."""
    try:
        return int(value, 0)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid integer value: {value}") from e


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert firmware files to flash-style binary dumps."
    )
    parser.add_argument('input', type=Path, help='Input firmware path (.hex, .elf, .apj, .bin)')
    parser.add_argument('output', type=Path, help='Output binary path')
    parser.add_argument('--chip-part', help='Chip part number for flash defaults (e.g., STM32F427)')
    parser.add_argument(
        '--flash-start',
        type=_parse_int_arg,
        help='Flash base address (supports decimal or hex, e.g. 134217728 or 0x08000000)',
    )
    parser.add_argument(
        '--flash-size',
        type=_parse_int_arg,
        help='Flash size in bytes (supports decimal or hex)',
    )
    parser.add_argument(
        '--fill-value',
        type=_parse_int_arg,
        default=0xFF,
        help='Fill byte for empty flash regions (default: 0xFF)',
    )
    parser.add_argument('--objcopy-path', help='Path to objcopy executable')
    parser.add_argument('--bootloader', type=Path, help='Optional bootloader binary to overlay')
    parser.add_argument(
        '--bootloader-offset',
        type=_parse_int_arg,
        default=0,
        help='Bootloader offset in output binary (default: 0)',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable debug logging',
    )
    return parser


def _write_metadata_json(
    result: ConversionResult,
    firmware_name: str,
    chip_part: str | None,
) -> Path:
    """Write key conversion address ranges to Metadata.json beside output binary."""
    metadata_path = result.output_path.parent / 'Metadata.json'
    payload = {
        'firmware_name': firmware_name,
        'chip_part': chip_part,
        'flash_start': result.flash_start,
        'flash_size': result.flash_size,
        'data_start': result.data_start,
        'data_end': result.data_end,
    }
    metadata_path.write_text(json.dumps(payload, indent=2) + '\n')
    return metadata_path


def main(argv: list[str] | None = None) -> int:
    """Run command-line conversion."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not 0 <= args.fill_value <= 0xFF:
        parser.error('--fill-value must be between 0 and 255')

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(levelname)s: %(message)s')

    converter = BinaryConverter(objcopy_path=args.objcopy_path)
    result = converter.convert(
        input_path=args.input,
        output_path=args.output,
        chip_part=args.chip_part,
        flash_start=args.flash_start,
        flash_size=args.flash_size,
        fill_value=args.fill_value,
    )

    if not result.success:
        logger.error('Conversion failed: %s', result.error)
        return 1

    if args.bootloader:
        if not converter.add_bootloader(result.output_path, args.bootloader, args.bootloader_offset):
            logger.error('Bootloader overlay failed')
            return 2

    metadata_path = _write_metadata_json(
        result=result,
        firmware_name=args.input.stem,
        chip_part=args.chip_part,
    )

    logger.info(
        'Created %s and %s (flash_start=0x%08X flash_size=%d data_start=0x%08X data_end=0x%08X)',
        result.output_path,
        metadata_path,
        result.flash_start,
        result.flash_size,
        result.data_start,
        result.data_end,
    )
    return 0


if __name__ == "__main__":
    main()
