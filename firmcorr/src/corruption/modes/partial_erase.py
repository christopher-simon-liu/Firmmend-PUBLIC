"""Partial erase corruption mode."""


def apply_partial_erase(
	data: bytearray,
	target_bytes: int,
	affected_mask: bytearray,
	*,
	firmware_start: int,
	firmware_end: int,
) -> tuple[bytearray, int]:
	"""Apply partial erase corruption inside the meaningful firmware range."""
	region_size = firmware_end - firmware_start
	target_bytes = max(0, min(region_size, int(target_bytes)))

	if target_bytes == 0:
		return data, 0

	erase_end = firmware_start + target_bytes

	corrupted = 0
	for i in range(firmware_start, erase_end):
		data[i] = 0xFF
		affected_mask[i] = 1
		corrupted += 1

	return data, corrupted
