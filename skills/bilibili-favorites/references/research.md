# Bilibili Favorites: Research + Feasibility Notes

Goal for this skill:
- List favorite folders (created + optionally collected/subscribed)
- List items inside a folder (recent-first)
- Fetch a video transcript via official subtitle tracks when available

## GitHub References (avoid reinventing the wheel)

These projects are useful for endpoint discovery and fallback strategies (signing, auth, etc.):
- https://github.com/SocialSisterYi/bilibili-API-collect (curated web API endpoint list)
- https://github.com/Nemo2011/bilibili-api (Python SDK; includes auth helpers and WBI signing utilities)

## Endpoints Used By This Skill

Auth probe / current user:
- GET `https://api.bilibili.com/x/web-interface/nav`
  - Use to auto-detect `mid` (uid) from cookies.

Favorite folders:
- GET `https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid=<uid>&type=2&web_location=333.1387`
- GET `https://api.bilibili.com/x/v3/fav/folder/collected/list?up_mid=<uid>&pn=<pn>&ps=<ps>` (optional)

Folder items:
- GET `https://api.bilibili.com/x/v3/fav/resource/list?media_id=<folderId>&pn=<pn>&ps=20&order=mtime&type=0&platform=web&web_location=333.1387`

Video transcript (subtitles):
- GET `https://api.bilibili.com/x/web-interface/view?bvid=<bvid>`
  - Resolve `title`, `pages`, `cid` (for multi-part videos).
- GET `https://api.bilibili.com/x/player/v2?bvid=<bvid>&cid=<cid>`
  - Read `data.subtitle.subtitles[*].subtitle_url`.
- GET `<subtitle_url>`
  - Subtitle JSON: `body[*] = { from, to, content }`

## Known Risks / Fallback Plan

- Some Bilibili endpoints sometimes introduce WBI signing requirements.
  - If any endpoint starts returning a non-zero `code` mentioning signing/WBI, fallback options:
    - Reuse WBI signing logic from `Nemo2011/bilibili-api`.
    - Or capture a signed request via Playwright (network interception) and replay it.

## Manual Test Checklist (requires valid cookies)

1) Login probe:
- Run `bili_me.py` and confirm it reports logged-in + prints `mid`.

2) List folders:
- Run `bili_folders.py` and confirm `created` list is non-empty.

3) List items:
- Pick a `media_id` and run `bili_folder_items.py --order mtime --limit 20`.
- Confirm items include `bvid` + valid video URLs.

4) Transcript:
- Pick a `bvid` and run `bili_video_transcript.py --bvid <BV...> --timestamps`.
- Expect:
  - Exit code `0` with non-empty transcript, or
  - Exit code `2` if the video has no subtitle tracks (needs STT fallback outside this skill).
