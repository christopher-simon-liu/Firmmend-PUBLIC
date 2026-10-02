# Firmware Corruption Examples

Examples of corruption modes applied to a 256-byte firmware sample.
These patterns simulate failure modes encountered when dumping firmware from
damaged or degraded flash memory.

## Reference: Baseline (Uncorrupted) Firmware

| Region | Address | Contents |
|--------|---------|----------|
| Vector table | `0x00-0x1F` | ARM Cortex-M vectors (SP, Reset, NMI, HardFault) |
| Code | `0x20-0x5F` | Thumb-2 instructions |
| Strings | `0x60-0x9F` | "ArduCopter", "CubeOrange", etc. |
| Config | `0xA0-0xDF` | Structured data, `DEADBEEF` pattern |
| Padding | `0xE0-0xFF` | Zeros (unused flash) |

```
08000000  00 00 02 20 01 01 00 08 01 02 00 08 01 03 00 08   |... ............|
08000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  03 46 7B 60 BD E8 80 40 00 BF 4F F0 00 00 70 47   |.F{`...@..O...pG|
08000050  80 B5 00 AF 03 46 7B 60 BD E8 80 40 00 BF 4F F0   |.....F{`...@..O.|
08000060  41 72 64 75 43 6F 70 74 65 72 00 76 34 2E 35 2E   |ArduCopter.v4.5.|
08000070  30 00 43 75 62 65 4F 72 61 6E 67 65 00 53 54 4D   |0.CubeOrange.STM|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000D0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000E0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
080000F0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
```

**File size: 256 bytes (0x100)**

## Partial Dump

**Pattern:** File is truncated, missing bytes at the end

**Mechanism:** The dump tool reads sequentially until something fails (timeout,
disconnect, crash). The resulting file is simply shorter than expected. Unlike
partial write, there's no `0xFF` padding. The bytes are just gone.

```
08000000  00 00 02 20 01 01 00 08 01 02 00 08 01 03 00 08   |... ............|
08000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  03 46 7B 60 BD E8 80 40 00 BF 4F F0 00 00 70 47   |.F{`...@..O...pG|
08000050  80 B5 00 AF 03 46 7B 60 BD E8 80 40 00 BF 4F F0   |.....F{`...@..O.|
08000060  41 72 64 75 43 6F 70 74 65 72 00 76 34 2E 35 2E   |ArduCopter.v4.5.|
08000070  30 00 43 75 62 65 4F 72 61 6E 67 65 00 53 54 4D   |0.CubeOrange.STM|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD         |..............|
```

**File size: 206 bytes** (expected 256) — **50 bytes missing!**

## Partial Write 

**Pattern:** Valid data at LOW addresses, `0xFF` at HIGH addresses

**Mechanism:** Flash was erased (all `0xFF`), then write started but didn't finish.
The beginning was written successfully, but later addresses remain in erased state.
Unlike partial dump, the file is full-size.

```
08000000  00 00 02 20 01 01 00 08 01 02 00 08 01 03 00 08   |... ............|
08000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  03 46 7B 60 BD E8 80 40 00 BF 4F F0 00 00 70 47   |.F{`...@..O...pG|
08000050  80 B5 00 AF 03 46 7B 60 BD E8 80 40 00 BF 4F F0   |.....F{`...@..O.|
08000060  41 72 64 75 43 6F 70 74 65 72 00 76 34 2E 35 2E   |ArduCopter.v4.5.|
08000070  30 00 43 75 62 65 4F 72 61 6E 67 65 00 53 54 4D   |0.CubeOrange.STM|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD FF FF   |................|
080000D0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
080000E0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
080000F0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
```

**File size: 256 bytes** (full size, but trailing bytes are `0xFF`, writing stopped at `0xCE`)

## Partial Erase

**Pattern:** `0xFF` at LOW addresses, Valid data at HIGH addresses

**Mechanism:** Flash erase operations typically progress from low addresses to high.
If interrupted (power loss, abort), low addresses are erased while high addresses
retain their original data.

```
08000000  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000010  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  03 46 7B 60 BD E8 80 40 00 BF 4F F0 00 00 70 47   |.F{`...@..O...pG|
08000050  80 B5 00 AF 03 46 7B 60 BD E8 80 40 00 BF 4F F0   |.....F{`...@..O.|
08000060  41 72 64 75 43 6F 70 74 65 72 00 76 34 2E 35 2E   |ArduCopter.v4.5.|
08000070  30 00 43 75 62 65 4F 72 61 6E 67 65 00 53 54 4D   |0.CubeOrange.STM|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000D0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000E0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
080000F0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
```

**File size: 256 bytes** (full size, but vector table erasesd to `0xFF`)

## Bit Flip

**Pattern:** A few scattered flipped bits (much less dense than exhausted cycles)

**Mechanism:** Read disturb / marginal cells / transient errors can flip a small number
of bits without the heavy stuck-bit / clustered failure patterns seen in severely worn
flash.

```
08000000  00 00 02 20 01 01 00 08 01 02 00 08 01 03 00 08   |... ............|
08000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  03 46 7B 60 BD E8 80 40 00 BF 4F F0 00 00 70 47   |.F{`...@..O...pG|
08000050  80 B5 00 AF 03 46 7B 60 BD E8 80 40 00 BF 4F F0   |.....F{`...@..O.|
08000060  41 72 64 75 43 6F 70 74 65 72 00 76 34 2E 35 2E   |ArduCopter.v4.5.|
08000070  30 00 43 75 62 65 4F 72 61 6E 67 65 00 53 54 4D   |0.CubeOrange.STM|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000D0  DE AD BE EF DE AD BE EF DE AD BE EF DE AD BE EF   |................|
080000E0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
080000F0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
```

**File size: 256 bytes** (full size, sparse bit level errors)

## 4. Address Bit Freeze (Address Line Fault)

**Pattern:** Equidistant bands / aliasing across the address space

**Mechanism:** One or two address lines on the bus between the reader and the
flash chip are stuck at 0 or 1 due to a solder bridge, broken trace, or damaged pin.
This causes address aliasing: multiple requested addresses map to the same physical address range, 
producing periodic bands of repeated data (or `0xFF` if mapped out of range).

```
08000000  00 00 02 20 01 01 00 08 01 02 00 08 01 03 00 08   |... ............|
08000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00   |................|
08000020  00 BF 4F F0 00 00 70 47 80 B5 00 AF 03 46 7B 60   |..O...pG.....F{`|
08000030  BD E8 80 40 00 BF 4F F0 00 00 70 47 80 B5 00 AF   |...@..O...pG....|
08000040  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000050  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000060  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000070  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
08000080  33 32 48 37 34 33 00 46 49 52 4D 57 41 52 45 00   |32H743.FIRMWARE.|
08000090  43 4F 4E 46 49 47 00 50 41 52 41 4D 53 00 00 00   |CONFIG.PARAMS...|
080000A0  01 00 00 00 00 10 00 00 FF 00 00 00 48 41 4C 00   |............HAL.|
080000B0  00 80 00 20 00 00 02 00 12 34 56 78 AB CD EF 01   |... .....4Vx....|
080000C0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
080000D0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
080000E0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
080000F0  FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF   |................|
```
**File size: 256 bytes** (full size, band of repeated data)

## Summary: Key Differences

| Corruption | File Size | LOW addresses | HIGH addresses |
|------------|-----------|---------------|----------------|
| **Partial Dump** | **Truncated** | Valid data | *Missing* |
| **Partial Write** | Full | Valid data | `0xFF` (unwritten) |
| **Partial Erase** | Full | `0xFF` (erased) | Valid data |
| **Bit flip** | Full | Bit errors | Bit errors |
| **Addr bit freeze** | Full | Aliased bands | Aliased bands |

## Corruption Levels

Severity **percentages (0-100)** for each corruption mode

### Partial Dump
| Percent | Level | Scenario |
|------|------------| --------------------- |
| 0 | Baseline | No corruption |
| 5 | Minor damage | Dump nearly complete; last few KB missing |
| 20 | Moderate damage | Connection dropped with significant data remaining
| 50 | Heavy damage | Half the flash was read before failure |

### Partial Write
| Percent | Level | Scenario |
|------|------------| --------------------- |
| 0 | Baseline | No corruption |
| 5 | Minor damage | Write interrupted near the very end (almost complete) |
| 20 | Moderate damage | Write stopped partway through; device has partial firmware |
| 50 | Heavy damage | Less than half the firmware was written |

** partial_write=5% means 95% of the firmware was successfully written **

### Partial Erase
| Percent | Level | Scenario |
|------|------------| --------------------- |
| 0 | Baseline | No corruption |
| 5 | Minor damage | Single sector erase interrupted almost immediately |
| 20 | Moderate damage | Multi-sector erase progressed a few pages before power loss |
| 50 | Heavy damage | Chip erase made significant progress before interruption |


### Bit Flip
| Percent | Level | Scenario |
|------|------------| --------------------- |
| 0 | Baseline | No corruption |
| 0.01 | Minor damage | Moderately worn flash or post-thermal-extraction (chip-off) |
| 0.1 | Moderate damage | Heavily worn flash or poor extraction conditions |
| 1 | Heavy damage | Severely degraded; approaching practical analysis limits |

### Addr Bit Freeze
| Percent | Level | Scenario |
|------|------------| --------------------- |
| 0 | Baseline | No corruption |
| 5 | Minor damage | Small bands of `0xFF` |
| 20 | Moderate damage | Mediums bands of `0xFF` |
| 50 | Heavy damage | Large bands of `0xFF` |

** Percentage of addresses aliased **