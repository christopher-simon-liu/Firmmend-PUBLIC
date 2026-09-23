"""Address-line bit-freeze corruption mode."""

from random import Random


def apply_address_bit_freeze(
    data: bytearray,
    target_bytes: int,
    affected_mask: bytearray,
    *,
    firmware_start: int,
    firmware_end: int,
    rng: Random,
) -> tuple[bytearray, int]:
    """Apply address-line faults to a severity-sized subset of firmware bytes.

    The stuck bit positions and values are derived from rng so runs are reproducible
    with the same seed. `target_bytes` controls how many addresses are remapped.
    """
    region_size = firmware_end - firmware_start
    target_bytes = max(0, min(region_size, int(target_bytes)))
    if region_size <= 1 or target_bytes == 0:
        return data, 0

    before = bytes(data)
    bit_max = max(0, (region_size - 1).bit_length() - 1)
    bitpos_1 = rng.randint(0, bit_max)
    bitval_1 = rng.randint(0, 1)

    use_second_bit = bit_max > 0 and target_bytes > max(1, region_size // 3)
    if use_second_bit:
        candidates = [b for b in range(bit_max + 1) if b != bitpos_1]
        bitpos_2 = rng.choice(candidates)
        bitval_2 = rng.randint(0, 1)
    else:
        bitpos_2 = -1
        bitval_2 = 0

    def freeze(addr: int, bitpos: int, bitval: int) -> int:
        if bitpos < 0:
            return addr
        mask = 1 << bitpos
        return (addr | mask) if bitval == 1 else (addr & ~mask)

    remap_plan: list[tuple[int, int]] = []
    for idx in range(firmware_start, firmware_end):
        local = idx - firmware_start
        mapped_local = freeze(local, bitpos_1, bitval_1)
        mapped_local = freeze(mapped_local, bitpos_2, bitval_2)
        if mapped_local == local:
            continue
        remap_plan.append((idx, firmware_start + mapped_local))

    if not remap_plan:
        return data, 0

    chosen = rng.sample(remap_plan, min(target_bytes, len(remap_plan)))

    corrupted = 0
    for idx, mapped_idx in chosen:
        affected_mask[idx] = 1
        if firmware_start <= mapped_idx < firmware_end:
            data[idx] = before[mapped_idx]
        else:
            data[idx] = 0xFF
        if data[idx] != before[idx]:
            corrupted += 1

    return data, corrupted
