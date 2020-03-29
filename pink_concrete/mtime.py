def max_mtime_from_region(data: bytes) -> int:
    highest = 0
    index = 4096
    while index < 8192:
        timestamp_bytes = data[index:index+4]
        value = int.from_bytes(timestamp_bytes, byteorder='big')
        if value > highest:
            highest = value
        index += 4
    return highest
