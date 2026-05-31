# Brand icons

Self-hosted provider favicons used by `BrandIcons.tsx` in the Linked Accounts dialog.
All six are local — no third-party icon library, no runtime third-party requests.

## Files

| File          | Source                                                                                | Size      |
|---------------|---------------------------------------------------------------------------------------|-----------|
| `google.png`  | `https://www.google.com/favicon.ico` → `sips -s format png`                            | 32×32     |
| `yahoo.png`   | `https://icons.duckduckgo.com/ip3/yahoo.com.ico` → `sips -s format png`                | 48×48     |
| `sleeper.png` | `https://sleeper.com/favicon.ico` → `sips -s format png`                               | 48×48     |
| `espn.png`    | `https://icons.duckduckgo.com/ip3/espn.com.ico` → `sips -s format png`                 | 64×64     |
| `nfl.png`     | `https://icons.duckduckgo.com/ip3/nfl.com.ico` → `sips --resampleHeightWidth 128 128`  | 128×128   |
| `cbs.png`     | `https://www.cbssports.com/apple-touch-icon.png`                                       | 60×60     |

## Refreshing

If a provider rebrands or updates their logo, refetch the source, convert
to PNG if needed (browsers handle ICO too, but PNG is more universally clean),
and drop into this folder with the same filename.
