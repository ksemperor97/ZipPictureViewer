# Zip Picture Viewer

여러 폴더와 ZIP/CBZ 안의 이미지를 하나의 연속된 목록처럼 넘겨 보는 데스크톱 이미지 뷰어입니다. 손상된 이미지나 아카이브 하나가 있어도 나머지 감상을 계속할 수 있도록 스캔·디코드·화면 상태를 분리해 처리합니다.

## 주요 기능

- 폴더 또는 단일 `.zip`/`.cbz` 파일을 열기와 드래그 앤 드롭으로 엽니다.
- 선택한 폴더 아래의 ZIP/CBZ와 일반 이미지 폴더를 한 번에 스캔하고 자연 정렬합니다.
- 이미지 단위와 묶음 단위로 이동하며 마지막 항목에서는 처음으로 순환합니다.
- GIF 애니메이션을 재생하고, 정지 이미지는 화면 맞춤·100%·확대/축소·드래그 이동을 지원합니다.
- 스캔과 이미지 디코드를 UI 밖에서 실행합니다. 새 루트를 열면 이전 스캔은 취소되고 최신 결과만 적용됩니다.
- 손상 ZIP, 읽기 실패 이미지, 자원 한도 초과 항목은 다른 파일을 막지 않고 `오류` 목록에 누적됩니다.
- ZIP의 UTF-8/CP437 이름과 레거시 CP949 한글 이름을 처리합니다. 현재 보고 있는 아카이브의 이름 해석을 메뉴에서 직접 바꿀 수 있습니다.
- 전통적인 ZipCrypto 암호는 실행 중 메모리에만 보관합니다. AES 암호화 ZIP은 명시적인 미지원 오류를 표시합니다.
- 최근 루트와 정확한 ZIP 레코드 위치를 원자적으로 저장하고 다음 실행 때 복원합니다.
- 실행 중 바뀐 파일은 revision을 확인해 오래된 캐시·비동기 결과를 폐기합니다.

## 지원 환경

| 환경 | 지원 범위 |
|---|---|
| macOS 13 이상, Apple Silicon | 앱 번들 및 소스 실행 |
| Windows 10 22H2 이상 / Windows 11, x64 | 앱 번들 및 소스 실행 |
| Linux | 소스 실행 best-effort |

배포 파일은 [GitHub Releases](https://github.com/ksemperor97/ZipPictureViewer/releases)에서 제공합니다. `v1.1.0`의 파일명은 다음 형식입니다.

- `ZipPictureViewer-v1.1.0-mac-arm64-slim.zip`
- `ZipPictureViewer-v1.1.0-windows-x64.zip`
- 각 ZIP과 함께 배포되는 `.sha256` 파일

공식 릴리스에 위 파일이 게시되기 전에는 소스 빌드 또는 CI artifact를 사용하세요. macOS에서 보안 경고가 나오면 Finder에서 앱을 우클릭한 뒤 `열기`를 선택할 수 있습니다. 정식 notarization 릴리스는 일반 더블클릭 실행을 기준으로 검증합니다.

## 지원 형식과 제한

지원 컨테이너는 `.zip`, `.cbz`, 일반 폴더입니다. 지원 이미지 확장자는 `.bmp`, `.gif`, `.jpeg`, `.jpg`, `.png`, `.webp`입니다.

안전한 기본 상한은 다음과 같습니다.

- 이미지 한 개의 비압축 입력: 256 MiB
- 원본 이미지 크기: 100 MP
- 한 번에 디코드하는 픽셀 버퍼 추정치: 256 MiB
- 64 MiB 이상인 ZIP 멤버의 압축률: 최대 500배
- 정지 이미지 캐시: 256 MiB

화면 맞춤과 사전 로딩은 viewport 크기에 맞춰 축소 디코드합니다. 100% 보기 또는 확대가 필요할 때 더 높은 해상도를 별도로 요청하며, 원본 로드가 한도를 넘거나 실패하면 기존 화면 맞춤 이미지를 유지합니다.

다음 형식은 현재 지원하지 않습니다.

- `.rar`, `.7z`
- HEIC, AVIF, TIFF
- AES 암호화 ZIP

ZIP 이름의 UTF-8 flag를 항상 우선합니다. flag가 없는 이름의 CP949 자동 감지는 휴리스틱이므로 잘못 해석되면 floating 메뉴의 `ZIP 이름` 선택을 해당 아카이브에 맞게 변경하세요.

## 조작법

| 입력 | 동작 |
|---|---|
| `←` / `→`, `Space` | 이전 / 다음 이미지 |
| `↑` / `↓` | 이전 / 다음 묶음 |
| `Command + ↑/↓` (macOS) | 이전 / 다음 형제 폴더 또는 형제 아카이브 |
| `Ctrl + ↑/↓` (Windows/Linux) | 이전 / 다음 형제 폴더 또는 형제 아카이브 |
| `O` | 폴더 열기 |
| `Ctrl + Shift + O` | ZIP/CBZ 열기 |
| `R` | 현재 루트 새로고침 |
| `0` | 화면 맞춤 |
| `1` | 100% 보기 |
| `+` / `-`, 마우스 휠 | 확대 / 축소 |
| 이미지 더블클릭 | 화면 맞춤 / 100% 전환 |
| `F` | 전체화면 전환 |
| `Esc` | 전체화면 종료 |

확대 상태에서는 이미지를 드래그해 이동합니다. 화면 맞춤 상태에서 이미지 영역을 드래그하면 프레임리스 창을 움직일 수 있고, 오른쪽 아래 손잡이로 창 크기를 바꿀 수 있습니다. floating 메뉴는 마우스를 움직이면 나타났다가 자동으로 숨습니다.

## 오류와 복구

- 손상된 이미지에서는 이전 픽스맵을 지우고 현재 파일명·위치와 오류 placeholder를 표시합니다. 탐색 버튼은 계속 사용할 수 있습니다.
- 읽지 못한 ZIP/CBZ는 `오류` 목록에 남기고 다른 컨테이너를 계속 읽습니다.
- `새로고침`은 현재 위치 ID를 기준으로 다시 스캔하며 교체된 파일과 캐시를 갱신합니다.
- 스캔 도중 `스캔 취소`를 누르거나 다른 루트를 열 수 있습니다. 이미 시작된 단일 ZIP 메타데이터 읽기는 다음 안전 지점에서 종료됩니다.
- 새 루트가 사라지거나 스캔 자체가 실패하면 기존 루트·목록·화면을 그대로 유지합니다.
- 빈 폴더, 미지원 형식만 있는 폴더, 읽지 못한 컨테이너를 서로 다른 메시지로 표시합니다.

## 소스에서 실행

Python 3.10 이상이 필요합니다. 개발 및 패키징 기준은 Python 3.12입니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m zippictureviewer
```

설치 후에는 다음 명령도 사용할 수 있습니다.

```bash
zip-picture-viewer
```

일부 Homebrew Python에서 `pyexpat`이 잘못된 시스템 `libexpat`을 읽는다면 실행 전에 다음을 지정하세요.

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:$DYLD_LIBRARY_PATH"
```

## 검증

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q zippictureviewer zippictureviewer_launcher.py
.venv/bin/python -m pip check
.venv/bin/python -m zippictureviewer --smoke-test
```

`--smoke-test`는 Qt GUI 초기화, GIF/JPEG/PNG/WebP 플러그인, 임시 ZIP 스캔, PNG 디코드, 세션 쓰기를 검사하고 이벤트 루프에 들어가지 않은 채 종료합니다. 패키징 스크립트는 생성한 실제 `.app`/`.exe`에서도 이 검사를 실행합니다.

## macOS 앱 빌드

호환 wheel을 고정한 별도 패키징 환경을 권장합니다.

```bash
python3.12 -m venv .venv-package
source .venv-package/bin/activate
python -m pip install -c constraints/packaging.txt -e ".[dev]"
PACKAGING_PYTHON="$PWD/.venv-package/bin/python" scripts/build_macos_app.sh
```

기본 개발 빌드(ad-hoc 서명)의 생성 결과:

```text
dist/ZipPictureViewer.app
dist/ZipPictureViewer-v1.1.0-mac-<arch>-slim-adhoc.zip
dist/ZipPictureViewer-v1.1.0-mac-<arch>-slim-adhoc.zip.sha256
```

빌드는 필수 Qt 플러그인, 깨진 심볼릭 링크, 엄격한 코드서명, 모든 Mach-O의 `minos <= 13.0`, 앱 내부 smoke test를 검사합니다. 일반 개발 빌드는 ad-hoc 서명을 사용합니다. Developer ID와 notarization을 요구하는 정식 릴리스 절차 및 필요한 환경변수는 [릴리스 체크리스트](docs/RELEASE_CHECKLIST.md)를 따릅니다.

## Windows 앱 빌드

Windows PowerShell에서 실행합니다.

```powershell
py -3.12 -m venv .venv-package
.\.venv-package\Scripts\Activate.ps1
python -m pip install -c constraints/packaging.txt -e ".[dev]"
scripts\build_windows_app.ps1
```

생성 결과:

```text
dist/ZipPictureViewer/ZipPictureViewer.exe
dist/ZipPictureViewer-v1.1.0-windows-x64.zip
dist/ZipPictureViewer-v1.1.0-windows-x64.zip.sha256
```

빌드는 `qwindows`, GIF/JPEG/WebP 플러그인, EXE ProductVersion, ZIP 구조·CRC, 앱 내부 smoke test를 검사합니다. Authenticode 서명을 릴리스 게이트로 강제하려면 `ZIP_PICTURE_VIEWER_REQUIRE_SIGNATURE=1`을 설정합니다.

## 세션 파일

- macOS: `~/Library/Application Support/ZipPictureViewer/session.json`
- Windows: `%APPDATA%\ZipPictureViewer\session.json`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/ZipPictureViewer/session.json`

세션 파일은 임시 파일에 먼저 기록한 뒤 원자적으로 교체합니다. 심볼릭 링크로 연 루트는 논리 경로 문맥을 유지하고, 저장된 항목이 사라지면 같은 컨테이너의 가장 가까운 항목부터 복원합니다.
