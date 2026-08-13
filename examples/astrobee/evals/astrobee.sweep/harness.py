"""check_and_fill_line(value_map, config_file_line) takes two arguments —
unpack the fixture row."""


def fill_config_line(row, ctx):
    return ctx.entrypoint(row["input"]["valueMap"], row["input"]["line"])
