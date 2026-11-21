# Solmara — The Poster for a Place That Isn't There

[![make.fun](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539.svg)](https://make.fun)

Solmara is a travel poster for a place that does not exist: the Isle of the
Second Sunset, a warm teal sea under one low golden sun, where a rose-glass
lighthouse stands on a dark sea stack and a single sailboat crosses water
glittering with the sun's path. The program draws the whole poster
procedurally — sky gradient, sun halo, lighthouse beam, clouds, headland,
sea, and the place name set in large cream capitals from a small vector
stroke font drawn by the program itself — using only the Python standard
library, with no network access and no external images.

## How to run

```sh
python3 main.py
```

This writes the poster to `/output/entry.png` (1024×1024 PNG, under 1 MiB).
A different output path can be given as the first argument, or a directory
can be named with the `MAKEFUN_OUTPUT_DIR` environment variable. The output
is deterministic: every run produces the same bytes.
