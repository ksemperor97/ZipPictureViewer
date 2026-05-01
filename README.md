# Zip Picture Viewer

여러 폴더에 흩어진 zip 파일 안의 이미지를 하나의 연속된 목록처럼 넘겨 보는 데스크톱 이미지 뷰어입니다.

## 다운로드

macOS Apple Silicon에서는 GitHub Release에서 앱 번들을 바로 받을 수 있습니다.

1. [ZipPictureViewer-v1.0.0-mac-arm64-slim.zip](https://github.com/ksemperor97/ZipPictureViewer/releases/download/v1.0.0/ZipPictureViewer-v1.0.0-mac-arm64-slim.zip)을 다운로드합니다.
2. zip을 풀고 `ZipPictureViewer.app`을 실행합니다.
3. macOS 보안 경고가 나오면 Finder에서 앱을 우클릭한 뒤 `열기`를 선택합니다.

Windows x64 빌드는 Release에 `ZipPictureViewer-v1.0.0-windows-x64.zip`으로 제공됩니다.

1. [ZipPictureViewer-v1.0.0-windows-x64.zip](https://github.com/ksemperor97/ZipPictureViewer/releases/download/v1.0.0/ZipPictureViewer-v1.0.0-windows-x64.zip)을 다운로드합니다.
2. zip을 풀고 `ZipPictureViewer/ZipPictureViewer.exe`를 실행합니다.
3. Windows 보안 경고가 나오면 `추가 정보`를 누른 뒤 `실행`을 선택합니다.

전체 릴리스 페이지: [Zip Picture Viewer v1.0.0](https://github.com/ksemperor97/ZipPictureViewer/releases/tag/v1.0.0)

## 기능

- 루트 폴더를 선택하면 하위 폴더의 `.zip`, `.cbz` 파일과 이미지 파일이 직접 들어있는 폴더를 재귀적으로 스캔합니다.
- zip 안의 이미지 파일과 일반 폴더 안의 이미지 파일을 자연 정렬로 이어 붙입니다.
- zip 안이나 일반 폴더 안의 GIF 파일은 애니메이션으로 재생합니다.
- 왼쪽/오른쪽 화살표 키 또는 버튼으로 이전/다음 이미지를 봅니다.
- 위/아래 화살표 키 또는 버튼으로 이전/다음 묶음(zip/cbz 또는 이미지 폴더)의 첫 이미지로 이동합니다.
- `Command + ↑/↓`(macOS) 또는 `Ctrl + ↑/↓`(Windows/Linux)로 현재 열어둔 폴더 기준 이전/다음 형제 폴더를 엽니다.
- floating 메뉴의 `이전 폴더`, `다음 폴더` 버튼으로도 형제 폴더를 이동합니다.
- 마지막 이미지에서 다음으로 이동하면 첫 이미지로 돌아갑니다.
- 마지막 묶음에서 다음 묶음으로 이동하면 첫 묶음으로 돌아가고, 첫 묶음에서 이전 묶음으로 이동하면 마지막 묶음으로 돌아갑니다.
- 한 묶음의 마지막 이미지에서 다음 묶음의 첫 이미지로 자연스럽게 넘어갑니다.
- 현재 위치, zip 파일명, 이미지 파일명을 표시합니다.
- 현재 이미지 주변의 앞뒤 이미지를 메모리에 미리 읽어 다음 이동을 빠르게 합니다.
- 마지막으로 보던 폴더와 이미지 위치를 OS별 사용자 설정 폴더에 저장하고 다음 실행 때 자동 복원합니다.
- floating 메뉴는 오른쪽 끝에 표시되고, 평소에는 숨겨져 있다가 마우스를 움직이면 잠깐 나타납니다.
- 일반 창도 제목줄 없는 프레임리스 모드로 표시됩니다. 이미지 영역을 드래그하면 창을 움직일 수 있고, 오른쪽 아래 작은 손잡이로 크기를 바꿀 수 있습니다.
- `F` 키 또는 전체화면 버튼으로 macOS 상단 메뉴바와 창 제목줄을 숨긴 전체화면 보기로 전환합니다. `Esc`로 창모드로 돌아옵니다.

## 실행

이 머신의 Homebrew Python은 `pyexpat`이 시스템 `libexpat`을 잘못 잡을 수 있어서, 아래처럼 Homebrew `expat` 경로를 먼저 지정하는 쪽이 안전합니다.

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:$DYLD_LIBRARY_PATH"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m zippictureviewer
```

또는 설치 후:

```bash
zip-picture-viewer
```

가상환경 생성이 어려운 환경에서는 다음처럼 현재 Python 환경에 설치해서 실행할 수도 있습니다.

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib:$DYLD_LIBRARY_PATH"
python3 -m pip install -e ".[dev]"
python3 -m zippictureviewer
```

## macOS 앱 빌드

```bash
source .venv/bin/activate
scripts/build_macos_app.sh
```

빌드 결과는 다음 위치에 생성됩니다.

```text
dist/ZipPictureViewer.app
```

## Windows 앱 빌드

Windows PowerShell에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
scripts\build_windows_app.ps1
```

빌드 결과는 다음 위치에 생성됩니다.

```text
dist/ZipPictureViewer/ZipPictureViewer.exe
dist/ZipPictureViewer-v1.0.0-windows-x64.zip
```

## macOS 상단 바

macOS의 화면 최상단 메뉴바는 일반 창 모드에서 앱 내부 위젯처럼 제거할 수 없는 시스템 영역입니다. 이 앱은 `F` 키 또는 `전체화면` 버튼으로 전체화면에 들어갈 때 AppKit presentation option을 적용해 메뉴바와 Dock을 자동 숨김 상태로 바꿉니다. 커서를 화면 위쪽으로 가져가면 macOS가 메뉴바를 다시 보여줍니다.

## 현재 범위

첫 버전은 표준 라이브러리로 안전하게 처리할 수 있는 `.zip`, `.cbz` 파일과 일반 이미지 폴더를 지원합니다. `.rar`/`.7z`는 별도 라이브러리 또는 시스템 도구 연동으로 확장할 수 있습니다.
