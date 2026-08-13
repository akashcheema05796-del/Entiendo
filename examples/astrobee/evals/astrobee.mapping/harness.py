"""parse_localization_log_str returns a (images, errors) tuple; fixture rows
compare JSON, so hand back [images, errors]."""


def parse_log_as_lists(row, ctx):
    return list(ctx.entrypoint(row["input"]))
