# 릴리스 체크리스트

이 문서는 `vX.Y.Z` 태그에서 재현 가능한 macOS·Windows 배포본을 만드는 절차와
검증 증거를 정의한다. 정식 릴리스는 GitHub Actions의 수동 release
workflow에서만 만든다.

## 1. 공통 사전 확인

- [ ] `pyproject.toml`의 버전이 릴리스 버전과 같다.
- [ ] 태그 이름이 정확히 `vX.Y.Z`이며 릴리스할 커밋을 가리킨다.
- [ ] 태그 커밋의 CI와 전체 테스트가 통과했다.
- [ ] GitHub Release를 태그에 맞춰 만들었다.
- [ ] 의존성 변경이 `constraints/packaging.txt`에 반영됐다.

두 release workflow는 요청한 태그를 직접 checkout하고
`scripts/check_release_version.py --tag ... --verify-head`로 버전과 HEAD를 다시
검증한다. 빌드된 앱에는 다음 파일이 포함되어야 한다.

- `build-provenance.json`: 버전, 정확한 commit SHA, clean/dirty 상태, manifest
  SHA-256
- `dependency-manifest.txt`: 빌드 환경에 설치된 Python 배포판과 버전
- `zip_picture_viewer-*.dist-info/METADATA`: 실행 중 사용하는 배포판 버전

validator는 위 세 버전·commit·manifest hash가 서로 맞는지 확인한다.

## 2. macOS 정식 릴리스

저장소 Actions secrets에 다음 값을 등록한다.

- `MACOS_CERTIFICATE_BASE64`: Developer ID Application 인증서와 private key를 담은
  PKCS#12 파일의 base64
- `MACOS_CERTIFICATE_PASSWORD`: PKCS#12 비밀번호
- `MACOS_SIGNING_IDENTITY`: `Developer ID Application: ... (TEAMID)` 전체 identity
- `MACOS_NOTARY_APPLE_ID`: 공증용 Apple ID
- `MACOS_NOTARY_TEAM_ID`: Apple Developer Team ID
- `MACOS_NOTARY_PASSWORD`: app-specific password

실행 절차:

1. Actions에서 **macOS Release** workflow를 선택한다.
2. `tag_name`에 정확한 태그를 입력한다.
3. GitHub Release에 올릴 때 `upload_to_release`를 켠다.
4. workflow가 아래 게이트를 모두 통과했는지 확인한다.
   - Developer ID 인증서 import와 identity 탐색
   - hardened runtime 및 secure timestamp 서명
   - `notarytool submit --wait`
   - `stapler staple`과 `stapler validate`
   - `spctl --assess --type execute`
   - 패키지 자체 `--smoke-test`

정식 산출물 이름은
`ZipPictureViewer-vX.Y.Z-mac-<arm64|x64|universal2>-slim.zip`이며 같은 이름에
`.sha256`을 붙인 체크섬 파일이 함께 생성된다.

`scripts/build_macos_app.sh`의 기본 모드는 로컬·PR 검증용 ad-hoc 서명이다. 이때
산출물은 `*-slim-adhoc.zip`으로 명명되며 정식 릴리스에 올리면 안 된다.
`REQUIRE_RELEASE_SIGNING=1`인 정식 모드는 signing identity 또는 notarytool
profile이 없으면 빌드를 시작하지 않고 실패한다.

## 3. Windows 정식 릴리스

1. Actions에서 **Windows Release** workflow를 선택한다.
2. `tag_name`에 정확한 태그를 입력한다.
3. GitHub Release에 올릴 때 `upload_to_release`를 켠다.
4. package validator, 실행 파일 `--smoke-test`, ZIP CRC 검증이 통과했는지 확인한다.

산출물은 `ZipPictureViewer-vX.Y.Z-windows-x64.zip`과
`ZipPictureViewer-vX.Y.Z-windows-x64.zip.sha256`이다. Authenticode를 필수로 하는
환경은 빌드 시 `ZIP_PICTURE_VIEWER_REQUIRE_SIGNATURE=1`을 설정해야 한다.

## 4. 배포 전 최종 검증

- [ ] workflow artifact와 GitHub Release에 ZIP과 `.sha256`이 모두 있다.
- [ ] 체크섬을 독립적으로 확인했다.

```bash
shasum -a 256 -c ZipPictureViewer-vX.Y.Z-mac-arm64-slim.zip.sha256
```

```powershell
$Expected = (Get-Content .\ZipPictureViewer-vX.Y.Z-windows-x64.zip.sha256).Split(' ')[0]
$Actual = (Get-FileHash .\ZipPictureViewer-vX.Y.Z-windows-x64.zip -Algorithm SHA256).Hash.ToLower()
if ($Expected -ne $Actual) { throw "SHA-256 mismatch" }
```

- [ ] 다운로드한 macOS 앱을 지원 최저 버전(macOS 13)에서 실행했다.
- [ ] 다운로드한 Windows 앱을 Windows 10 22H2와 Windows 11에서 실행했다.
- [ ] 폴더 열기, ZIP/CBZ 열기, 앞뒤 이동, GIF 재생을 각 플랫폼에서 확인했다.
- [ ] macOS에서는 `spctl --assess --type execute --verbose=4`가 accepted를 반환한다.
- [ ] 릴리스 노트에 commit SHA와 두 ZIP의 SHA-256을 기록했다.

## 5. 릴리스 증거 기록

릴리스 이슈나 PR에 다음 값을 남긴다.

```text
Tag:
Commit SHA:
macOS workflow run:
macOS artifact SHA-256:
macOS 13 launch check:
Windows workflow run:
Windows artifact SHA-256:
Windows 10/11 launch check:
Known limitations:
```
