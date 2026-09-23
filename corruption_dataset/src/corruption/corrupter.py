"""
Firmware corruption engine.

Applies various corruption patterns to firmware binaries to simulate
real-world data corruption scenarios.

Corruption Types:
partial_dump - Read operation ended early (truncated data)
partial_write - Write operation ended early
partial_erase - Sections contain 0xFF or 0x00 (erased flash)
bit_flip - Sparse random bit flips (read disturb, minor errors)
"""

import argparse
import logging
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from modes.partial_dump import apply_partial_dump   
from modes.partial_write import apply_partial_write
from modes.partial_erase import apply_partial_erase
from modes.bit_flip import apply_bit_flip
from modes.address_bit_freeze import apply_address_bit_freeze

logger = logging.getLogger(__name__)

SUPPORTED_MODES = ('partial_erase', 'partial_dump', 'partial_write', 'bit_flip', 'address_bit_freeze')
RANDOM_SEED = [1.048596, 1.129848, 0.409420]

@dataclass
class CorruptionParams:
    """Parameters for corruption application."""
    partial_erase: str | int = "0%"
    partial_dump: int = 0
    partial_write: str | int = "0%"
    bit_flip: str | int = "0%"
    address_bit_freeze: str | int = "0%"


@dataclass
class CorruptionResult:
    """Result of corruption application."""
    success: bool
    output_path: Path | None
    corruptions_applied: list[str]
    bytes_corrupted: int
    affected_by_type: dict[str, bytearray]
    final_size: int
    error: str | None = None


class CorruptionEngine:
    """Apply selected corruption patterns to firmware binaries."""

    def __init__(
        self,
        seed: float = 1.048596
    ):
        self.rng = random.Random(seed)

    def corrupt(
        self,
        input_path: Path,
        output_path: Path,
        params: CorruptionParams,
        *,
        firmware_start: int | None = None,
        firmware_end: int | None = None,
    ) -> CorruptionResult:
        try:
            # Read input
            data = bytearray(input_path.read_bytes())
            original_size = len(data)
            firmware_start, firmware_end = self._normalize_firmware_bounds(
                original_size,
                firmware_start,
                firmware_end,
            )
            firmware_size = firmware_end - firmware_start

            corruptions_applied = []
            total_corrupted = 0
            affected_by_type: dict[str, bytearray] = {
                ctype: bytearray(original_size) for ctype in SUPPORTED_MODES
            }
            final_size = original_size

            partial_erase_bytes = self._parse_amount_spec(
                params.partial_erase,
                total_units=firmware_size,
            )
            if partial_erase_bytes > 0:
                data, corrupted = apply_partial_erase(
                    data,
                    partial_erase_bytes,
                    affected_by_type['partial_erase'],
                    firmware_start=firmware_start,
                    firmware_end=firmware_end,
                )
                total_corrupted += self._record_corruption(
                    corruptions_applied,
                    'partial_erase',
                    params.partial_erase,
                    corrupted,
                )

            partial_write_bytes = self._parse_amount_spec(
                params.partial_write,
                total_units=firmware_size,
            )
            if partial_write_bytes > 0:
                data, corrupted = apply_partial_write(
                    data,
                    partial_write_bytes,
                    affected_by_type['partial_write'],
                    firmware_start=firmware_start,
                    firmware_end=firmware_end,
                    rng=self.rng,
                    clamp_boundary=self._clamp_boundary_within_region,
                )
                total_corrupted += self._record_corruption(
                    corruptions_applied,
                    'partial_write',
                    params.partial_write,
                    corrupted,
                )

            bit_flip_bits = self._parse_amount_spec(
                params.bit_flip,
                total_units=original_size * 8,
            )
            if bit_flip_bits > 0:
                data, corrupted = apply_bit_flip(
                    data,
                    bit_flip_bits,
                    affected_by_type['bit_flip'],
                    rng=self.rng,
                )
                total_corrupted += self._record_corruption(
                    corruptions_applied,
                    'bit_flip',
                    params.bit_flip,
                    corrupted,
                )

            address_bit_freeze_bytes = self._parse_amount_spec(
                params.address_bit_freeze,
                total_units=firmware_size,
            )
            if address_bit_freeze_bytes > 0:
                data, corrupted = apply_address_bit_freeze(
                    data,
                    address_bit_freeze_bytes,
                    affected_by_type['address_bit_freeze'],
                    firmware_start=firmware_start,
                    firmware_end=firmware_end,
                    rng=self.rng,
                )
                total_corrupted += self._record_corruption(
                    corruptions_applied,
                    'address_bit_freeze',
                    params.address_bit_freeze,
                    corrupted,
                )

            if params.partial_dump > 0:
                partial_dump_bytes = self._parse_amount_spec(
                    f"{params.partial_dump}%",
                    total_units=firmware_size,
                )
                data, corrupted, truncate_at = apply_partial_dump(
                    data,
                    partial_dump_bytes,
                    affected_by_type['partial_dump'],
                    firmware_start=firmware_start,
                    firmware_end=firmware_end,
                    rng=self.rng,
                    clamp_boundary=self._clamp_boundary_within_region,
                )
                if corrupted > 0:
                    corruptions_applied.append(f"partial_dump:{params.partial_dump}%")
                    total_corrupted += corrupted
                    final_size = truncate_at
                    self._clear_truncated_masks(affected_by_type, truncate_at)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)

            logger.info(
                f"Applied {len(corruptions_applied)} corruption types, "
                f"{total_corrupted} bytes affected"
            )

            return CorruptionResult(
                success=True,
                output_path=output_path,
                corruptions_applied=corruptions_applied,
                bytes_corrupted=total_corrupted,
                affected_by_type=affected_by_type,
                final_size=final_size
            )

        except Exception as e:
            logger.error(f"Corruption failed: {e}")
            return CorruptionResult(
                success=False,
                output_path=None,
                corruptions_applied=[],
                bytes_corrupted=0,
                affected_by_type={},
                final_size=0,
                error=str(e)
            )

    @staticmethod
    def _record_corruption(
        corruptions_applied: list[str],
        mode: str,
        value: str | int,
        corrupted: int,
    ) -> int:
        """Record a mode result and return bytes to add to the global tally."""
        if corrupted <= 0:
            return 0
        corruptions_applied.append(f"{mode}:{value}")
        return corrupted

    @staticmethod
    def _clear_truncated_masks(affected_by_type: dict[str, bytearray], truncate_at: int) -> None:
        """Masks should only describe bytes that still exist in the truncated output."""
        for ctype, mask in affected_by_type.items():
            if ctype == 'partial_dump' or truncate_at >= len(mask):
                continue
            mask[truncate_at:] = b'\x00' * (len(mask) - truncate_at)

    def _normalize_firmware_bounds(
        self,
        size: int,
        firmware_start: int | None,
        firmware_end: int | None,
    ) -> tuple[int, int]:
        if firmware_start is None:
            firmware_start = 0
        if firmware_end is None:
            firmware_end = size

        firmware_start = max(0, min(size, int(firmware_start)))
        firmware_end = max(firmware_start, min(size, int(firmware_end)))
        if firmware_end <= firmware_start:
            return 0, size
        return firmware_start, firmware_end

    def _clamp_boundary_within_region(
        self,
        boundary: int,
        region_start: int,
        region_end: int,
    ) -> int | None:
        region_size = region_end - region_start
        if region_size <= 1:
            return None

        lower_bound = region_start + 1
        upper_bound = region_end - 1
        return max(lower_bound, min(upper_bound, boundary))

    def _parse_amount_spec(self, spec: str | int, *, total_units: int) -> int:
        """Convert an absolute or percent spec into a clamped unit count."""
        if total_units <= 0:
            return 0

        if spec is None:
            return 0

        if isinstance(spec, int):
            return max(0, min(total_units, spec))

        s = str(spec).strip()
        if s == "":
            return 0

        if s.endswith("%"):
            num = s[:-1].strip()
            if num == "":
                return 0
            pct = float(num)
            units = int(round(total_units * (pct / 100.0)))
            if pct > 0.0 and units == 0:
                units = 1
            return max(0, min(total_units, units))

        units = int(s)
        return max(0, min(total_units, units))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Apply one firmware corruption mode to a binary.'
    )
    parser.add_argument('--input-binary', type=Path, help='Path to input binary')
    parser.add_argument('--random-seed', type=float, default=None, help='Random seed for reproducibility')
    parser.add_argument(
        '--mode',
        required=True,
        choices=SUPPORTED_MODES,
        help='Corruption mode to apply',
    )
    parser.add_argument(
        '--severity',
        type=_parse_severity,
        required=True,
        help='Severity as fraction from 0.0 to 1.0 (e.g., 0.1)',
    )
    parser.add_argument(
        '--firmware-start',
        type=_parse_int_value,
        default=None,
        help='Start offset of meaningful firmware bytes (decimal or hex, e.g., 4096 or 0x1000)',
    )
    parser.add_argument(
        '--firmware-end',
        type=_parse_int_value,
        default=None,
        help='Exclusive end offset of meaningful firmware bytes (decimal or hex)',
    )
    parser.add_argument('--output-folder', type=Path, required=True, help='Folder for corrupted output')
    return parser


def _parse_int_value(value: str) -> int:
    """Parse decimal or 0x-prefixed integers for CLI offset arguments."""
    try:
        parsed = int(value, 0)
    except ValueError as e:
        raise argparse.ArgumentTypeError('value must be an integer (decimal or hex)') from e
    if parsed < 0:
        raise argparse.ArgumentTypeError('value must be non-negative')
    return parsed


def _parse_severity(value: str) -> float:
    """Parse and validate severity as a normalized fraction in [0.0, 1.0]."""
    try:
        severity = float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError('severity must be a number in [0.0, 1.0]') from e
    if not 0.0 <= severity <= 1.0:
        raise argparse.ArgumentTypeError('severity must be in [0.0, 1.0]')
    return severity


def _build_params_for_mode(mode: str, severity: float) -> CorruptionParams:
    severity_pct = severity * 100.0
    severity_spec = f'{severity_pct}%'
    if mode == 'partial_dump':
        return CorruptionParams(partial_dump=int(round(severity_pct)))

    by_mode = {
        'partial_erase': {'partial_erase': severity_spec},
        'partial_write': {'partial_write': severity_spec},
        'bit_flip': {'bit_flip': severity_spec},
        'address_bit_freeze': {'address_bit_freeze': severity_spec},
    }
    if mode not in by_mode:
        raise ValueError(f'unsupported mode: {mode}')
    return CorruptionParams(**by_mode[mode])


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if not args.input_binary.is_file():
        logger.error('Input binary not found: %s', args.input_binary)
        return 2

    try:
        params = _build_params_for_mode(args.mode, args.severity)
    except ValueError as e:
        logger.error(str(e))
        return 2

    args.output_folder.mkdir(parents=True, exist_ok=True)
    output_path = args.output_folder / f'{args.input_binary.stem}.{args.mode}-{args.severity}.bin'

    engine = CorruptionEngine(seed=args.random_seed)
    result = engine.corrupt(
        args.input_binary,
        output_path,
        params,
        firmware_start=args.firmware_start,
        firmware_end=args.firmware_end,
    )

    if not result.success:
        logger.error('Corruption failed: %s', result.error)
        return 1

    logger.info('Created %s', output_path)
    logger.info('Applied: %s', ', '.join(result.corruptions_applied) if result.corruptions_applied else 'none')
    logger.info('Bytes affected: %d', result.bytes_corrupted)
    return 0


if __name__ == "__main__":
    sys.exit(main())