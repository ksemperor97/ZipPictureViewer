# Zip Picture Viewer

여러 폴더와 ZIP/CBZ 안의 이미지를 하나의 연속된 목록처럼 넘겨 보는 macOS 전용 이미지 뷰어입니다. Swift와 AppKit으로 만든 네이티브 앱이며, 앱 크기는 약 1.3MB입니다.

> 2.0부터 Swift로 다시 만들었습니다. 1.x Python/PySide6 버전(macOS·Windows)은 `python-final` 태그에 그대로 남아 있습니다. 세션 파일 형식이 같아서 1.x에서 저장한 읽던 위치가 그대로 이어집니다.

## 주요 기능

- 폴더나 ZIP/CBZ를 창에 드롭하거나, 열기 창, Finder의 `다음으로 열기`, Dock 아이콘 드롭, 명령줄 경로로 엽니다.
- ZIP 하나를 열면 그 ZIP이 든 폴더 전체를 열고, 고른 ZIP의 첫 이미지부터 보여 줍니다. 그 ZIP 안에 저장된 위치가 있으면 거기서 이어 봅니다. 홈 폴더나 볼륨 최상위에 있는 ZIP은 넓은 스캔을 피하려고 그 ZIP만 엽니다.
- 폴더 아래의 ZIP/CBZ와 이미지 폴더를 한 번에 스캔하고 Finder처럼 자연 정렬합니다(`vol2` 다음 `vol10`).
- 큰 폴더는 고른 ZIP(또는 이어 볼 위치가 있는 묶음)을 먼저 읽어 바로 보여 주고, 나머지는 뒤에서 계속 읽습니다.
- 이미지 단위와 묶음 단위로 이동하며, 마지막 이미지 다음은 처음으로 돌아갑니다.
- 화면 맞춤, 100%, 확대/축소, 트랙패드 핀치, 더블클릭 전환을 지원합니다. 큰 이미지는 화면 크기로 줄여 디코드하고, 확대하면 원본 해상도를 따로 불러옵니다.
- GIF 애니메이션을 재생합니다. EXIF 회전 정보를 반영합니다.
- 손상된 이미지나 ZIP 하나가 있어도 나머지는 계속 볼 수 있습니다. 읽지 못한 항목은 `오류` 목록에 모입니다.
- 한글(CP949) 파일명 ZIP을 자동으로 인식하고, 필요하면 ZIP 이름 인코딩을 직접 바꿀 수 있습니다.
- 전통적인 ZipCrypto 암호 ZIP은 암호를 물어보고, 실행 중 메모리에만 보관합니다. AES 암호화 ZIP은 미지원 메시지를 표시합니다.
- 마지막으로 연 폴더와 정확한 ZIP 항목 위치를 기억해 다음 실행 때 복원합니다.

## 지원 형식과 제한

- 컨테이너: 폴더, `.zip`, `.cbz` (ZIP64 포함)
- 이미지: `.jpg` `.jpeg` `.png` `.gif` `.webp` `.bmp` `.heic` `.heif` `.avif` `.tif` `.tiff` (macOS ImageIO)
- 미지원: `.rar`, `.7z`, AES 암호화 ZIP

안전 상한: 이미지 한 개의 비압축 크기 256MiB, 원본 1억 픽셀, 64MiB 이상 ZIP 항목의 압축률 500배, ZIP 중앙 디렉터리 64MiB, ZIP 항목과 전체 목록 각각 10만 개, 이미지 캐시 256MiB.

## 조작법

| 입력 | 동작 |
|---|---|
| `←` / `→`, `Space` | 이전 / 다음 이미지 |
| `↑` / `↓` | 이전 / 다음 묶음 |
| `⌘↑` / `⌘↓` | 이전 / 다음 형제 폴더 또는 형제 아카이브 |
| `O`, `⌘O` | 폴더 열기 |
| `⇧⌘O` | ZIP/CBZ 열기 |
| `R`, `⌘R` | 새로고침 |
| `0` / `1` | 화면 맞춤 / 100% |
| `+` / `-`, 핀치 | 확대 / 축소 |
| 이미지 더블클릭 | 화면 맞춤 / 100% 전환 |
| `F`, `⌃⌘F` | 전체 화면 |
| `Esc` | 전체 화면 종료 |
| `?` | 단축키 도움말 |

화면 맞춤 상태에서 이미지를 드래그하면 창이 움직입니다. 마우스를 움직이면 아래쪽 조작 패널과 위쪽 파일 경로가 나타났다가 잠시 뒤 숨습니다. `펼치기`를 누르면 ZIP 열기, 폴더·묶음 이동, 확대, 오류, ZIP 이름 인코딩 같은 나머지 조작이 나옵니다.

## 빌드와 실행

macOS 13 이상, Swift 6 툴체인(Xcode 16 이상 또는 Command Line Tools)이 필요합니다.

```bash
swift run ZipPictureViewer
```

경로를 넘기면 바로 엽니다.

```bash
swift run ZipPictureViewer ~/Comics/Series/vol01.zip
```

앱 번들과 배포용 zip을 만듭니다. Xcode가 있으면 자동으로 사용합니다.

```bash
Scripts/build_app.sh
```

결과물은 `dist/ZipPictureViewer.app`과 `dist/ZipPictureViewer-v<버전>-mac.zip`입니다. Apple Silicon과 Intel을 함께 담은 유니버설 앱이며(`lipo`로 두 아키텍처와 최소 macOS 13.0을 확인), 여러 아키텍처 빌드에는 Xcode가 필요합니다. Command Line Tools만 있으면 `ARCHS=arm64`처럼 한 아키텍처만 지정합니다. 기본은 hardened runtime을 켠 ad-hoc 서명이며, `CODESIGN_IDENTITY`로 서명 인증서를 지정할 수 있습니다. 앱 안에서 디코더, ZIP 스캔, 세션 저장을 점검하려면 `--smoke-test`로 실행합니다.

Xcode에서 개발하려면 `Package.swift`를 열면 됩니다.

## 배포

정식 배포본은 Developer ID로 서명하고 Apple 공증(notarization)을 받은 유니버설 앱입니다.

### GitHub Actions로 배포

1. `VERSION`을 새 버전으로 올려 `main`에 병합합니다.
2. 같은 버전의 태그를 만들어 올립니다.

   ```bash
   git tag v2.0.0 && git push origin v2.0.0
   ```

3. Actions의 `Release` 워크플로를 `tag`에 `v2.0.0`을 넣어 실행합니다. 태그와 `VERSION`이 다르면 멈춥니다.

워크플로는 인증서를 임시 키체인에 넣고, 유니버설 앱을 빌드·서명한 뒤 `--smoke-test`(Rosetta로 Intel 쪽도)와 E2E 테스트를 앱 번들에 돌립니다. 통과하면 공증을 받아 티켓을 붙이고(`stapler`), `spctl`로 Gatekeeper 통과를 확인한 다음 zip을 그 태그의 GitHub 릴리스에 올립니다. 릴리스가 없으면 초안(draft)으로 만들므로, 내용을 확인한 뒤 직접 공개합니다. `upload_to_release`를 끄면 워크플로 아티팩트로만 남깁니다.

필요한 저장소 시크릿:

| 시크릿 | 내용 |
|---|---|
| `MACOS_CERTIFICATE_BASE64` | `Developer ID Application` 인증서와 개인 키를 내보낸 `.p12`의 base64 (`base64 -i cert.p12`) |
| `MACOS_CERTIFICATE_PASSWORD` | 그 `.p12`의 암호 |
| `MACOS_SIGNING_IDENTITY` | 서명 ID, 예: `Developer ID Application: 이름 (TEAMID)` |
| `MACOS_NOTARY_APPLE_ID` | 공증에 쓸 Apple ID |
| `MACOS_NOTARY_TEAM_ID` | 개발자 팀 ID |
| `MACOS_NOTARY_PASSWORD` | 그 Apple ID의 앱 암호(app-specific password) |

### 내 Mac에서 배포본 만들기

키체인에 Developer ID 인증서가 있고 `notarytool` 프로필을 저장해 두었다면 같은 과정을 로컬에서 할 수 있습니다.

```bash
xcrun notarytool store-credentials zpv-notary --apple-id <Apple ID> --team-id <TEAMID>
```

```bash
CODESIGN_IDENTITY="Developer ID Application: 이름 (TEAMID)" NOTARYTOOL_PROFILE=zpv-notary Scripts/build_app.sh
```

이미 서명한 앱만 공증하려면 `NOTARYTOOL_PROFILE=zpv-notary Scripts/notarize_app.sh`를 실행합니다. ad-hoc 서명이거나 hardened runtime이 없으면 제출 전에 멈추고, 공증이 거절되면 Apple의 로그를 출력합니다.

## 구조

| 위치 | 역할 |
|---|---|
| `Sources/ViewerCore` | UI 없는 핵심: 형식, 자연 정렬, ZIP 중앙 디렉터리·이름 인코딩·항목 읽기(Stored/Deflate/ZipCrypto), 스캔, 폴더 탐색, 세션 |
| `Sources/ZipPictureViewer` | AppKit 앱: 창 구성, 이미지 캔버스, ImageIO 디코더와 캐시, 스캔 적용, 조작 패널, 테스트용 자동화 채널 |
| `Scripts/build_app.sh`, `Resources/Info.plist` | 유니버설 빌드, 앱 번들 조립과 서명, Finder 문서 유형 선언 |
| `Scripts/notarize_app.sh`, `Scripts/package_app.sh` | 공증·staple·Gatekeeper 확인, 배포용 zip과 체크섬 |
| `.github/workflows` | CI(`ci.yml`), 서명·공증 배포(`release.yml`) |
| `tests/` | 실제 앱을 띄워 조작하는 E2E 테스트 |

## 테스트

테스트는 모두 실제 앱을 실행해서 확인하는 E2E 테스트입니다. 테스트마다 앱을 새로 띄워 실제 `NSEvent`(키, 마우스 클릭)와 드래그 앤 드롭을 보내고, 화면에 그려진 픽셀 색과 앱 상태를 확인한 뒤 종료합니다. 세션 복원은 앱을 실제로 껐다가 다시 켜서 확인합니다. 테스트 중에는 창이 화면에 나타났다 사라집니다.

```bash
python3 -m pip install -r tests/requirements.txt
python3 -m pytest -q
```

테스트 세션이 시작될 때 `swift build`로 디버그 앱을 만듭니다. 빌드한 앱 번들로 같은 시나리오를 돌리려면 실행 파일을 지정합니다. 이때는 `open -a`로 Finder와 같은 경로로 여는 시나리오도 함께 실행됩니다.

```bash
ZPV_E2E_APP="$PWD/dist/ZipPictureViewer.app/Contents/MacOS/ZipPictureViewer" python3 -m pytest -q
```

테스트는 앱을 숨은 `--automation-handshake` 옵션과 `ZIP_PICTURE_VIEWER_AUTOMATION_KEY` 환경변수를 함께 주어 실행할 때만 열리는 로컬(127.0.0.1) 제어 채널을 씁니다. 일반 실행에서는 이 채널이 열리지 않습니다.

## 세션 파일

`~/Library/Application Support/ZipPictureViewer/session.json`에 저장합니다. `ZIP_PICTURE_VIEWER_CONFIG_DIR`를 지정하면 그 폴더를 씁니다. 파일이 손상되면 빈 세션으로 시작하고, 저장에 실패해도 감상은 계속됩니다.
