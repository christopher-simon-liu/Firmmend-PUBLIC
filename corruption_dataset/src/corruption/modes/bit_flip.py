"""Sparse bit-flip corruption mode."""

from random import Random


def apply_bit_flip(
	data: bytearray,
	target_bits: int,
	affected_mask: bytearray,
	*,
	rng: Random,
) -> tuple[bytearray, int]:
	"""Apply sparse random bit flips."""
	size = len(data)
	total_bits = size * 8
	target_bits = max(0, min(total_bits, int(target_bits)))

	if target_bits == 0:
		return data, 0

	corrupted_bytes = 0
	bit_positions = rng.sample(range(total_bits), target_bits)
	for bit_idx in bit_positions:
		byte_idx = bit_idx // 8
		bit = bit_idx % 8
		before = data[byte_idx]
		after = before ^ (1 << bit)
		data[byte_idx] = after

		if after != before:
			if affected_mask[byte_idx] == 0:
				corrupted_bytes += 1
			affected_mask[byte_idx] = min(255, affected_mask[byte_idx] + 1)

	return data, corrupted_bytes
