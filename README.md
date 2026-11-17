# Market Memo · 시세 메모

업무 화면 구석에 조용히 띄워두는 작은 Windows 시세창입니다. **바이낸스 USDT-M 무기한 선물 종목을 검색·선택**하고 최근 체결가와 24시간 등락률을 확인할 수 있습니다.

## 기능

- 종목 입력창에서 `BTC`, `ETHUSDT`, `AKE/USDT`처럼 입력 후 **Enter** 또는 **변경**을 누릅니다. 목록에서 선택하면 바로 전환됩니다.
- 바이낸스 공개 종목 목록에서 현재 거래 중인 **USDT 무기한 선물**만 가져옵니다. 목록 조회 실패 시 직접 입력과 기본 목록을 사용할 수 있습니다.
- 코인 선물(`PERPETUAL`)과 주식·ADR 등 전통자산 선물(`TRADIFI_PERPETUAL`)을 모두 지원합니다. `SKHY` 또는 `SKHYUSDT`를 입력하면 하이닉스 ADR 추종 선물을 선택합니다. 국내 주식 추종 `SKHYNIXUSDT`와는 다른 종목입니다.
- 종목을 바꾸면 이전 가격을 즉시 지우고 새 시세를 받습니다. 이전 종목의 늦은 응답은 무시합니다.
- 기본 크기 286 × 200. 불투명도는 35~100%로 조절하며 처음 실행할 때는 100%입니다.
- **고정**을 켜면 다른 창 위에 표시됩니다. 제목 표시줄을 끌어 이동합니다.
- **Esc**로 최소화하고 작업 표시줄에서 복원합니다.
- 약 1초마다 공개 시세를 조회합니다. 응답이 늦으면 이전 요청이 끝난 뒤 조회하며, 실패하면 5~30초 간격으로 재시도합니다.
- KST 시세 시각을 표시합니다. 시세가 60초 이상 오래되면 지연 상태를, 연결에 실패하면 마지막 확인값임을 표시합니다.
- 선택 종목·위치·불투명도를 저장합니다. 알림, 소리, 자동 시작, 주문 기능이 없습니다. API 키나 계좌 연결도 필요하지 않습니다.

## 실행

Windows와 Tcl/Tk가 포함된 **Python 3.10 이상**이 필요합니다. 별도 pip 패키지는 사용하지 않습니다.

```powershell
py -3 ake_memo.py
```

또는 `start.cmd` / `AKE 메모 실행.cmd`를 실행합니다. Python이 PATH에 등록되어 있으면 콘솔 없이 실행됩니다. Codex 런타임이 있는 환경도 지원합니다.

## 확인 명령

```powershell
py -3 ake_memo.py --self-test
py -3 ake_memo.py --smoke-test
py -3 ake_memo.py --check --symbol BTCUSDT
py -3 ake_memo.py --list-symbols
```

앞의 두 검사는 인터넷을 사용하지 않습니다. `--smoke-test`는 숨겨진 Tk 창에서 종목 전환, 이전 응답 차단, 비활성 종목 거부와 불투명도 조절을 확인합니다. 뒤의 두 명령은 바이낸스 공개 API에 접속합니다.

## 데이터와 로컬 설정

가격은 현물이 아닌 **바이낸스 USDT-M 무기한 선물 최근 체결가**입니다. 마크가격과 다를 수 있습니다. 24시간 등락률은 바이낸스의 이동 24시간 기준입니다. 지역·방화벽·거래소 제한으로 연결하지 못할 수 있습니다.

- [24시간 시세 API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/24hr-Ticker-Price-Change-Statistics)
- [거래 종목 API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Exchange-Information)

실행 시 같은 폴더에 `settings.json`과 `status.json`이 생성됩니다. 개인 설정과 로컬 시세 상태이며 `.gitignore`에 포함되어 저장소에는 올리지 않습니다. 인증정보·개인정보를 입력할 필요가 없습니다.
