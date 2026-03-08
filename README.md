# VENDIX

디스코드 + 웹 기반 개인 상점(쇼핑몰) 운영 서비스입니다.  
이 프로젝트는 서버(길드) 단위로 상점을 만들고, 관리자 웹패널에서 상품/유저/충전/로그를 관리할 수 있게 설계되어 있습니다.

---

## 1. 이 프로그램이 하는 일 (한 줄 요약)

`디스코드로 서버 등록` + `웹에서 상점 운영` + `사용자 구매/충전`을 한 시스템으로 처리합니다.

---

## 2. 전체 구조

### 핵심 파일

- `app.py`
  - 디스코드 봇
  - 라이센스 생성/등록 같은 명령 처리
- `web.py`
  - Flask 웹 서버
  - 관리자 패널 + 상점 페이지 + 결제/충전 로직
- `util/database.py`
  - 서버 등록 시 DB 초기 생성
- `config.py` (로컬 전용, Git 제외)
  - 봇 토큰, GUILD_ID 설정

### 데이터베이스 구조

- 공용 DB: `db/database.db`
  - 라이센스 키 목록
- 서버별 DB: `db/<server_id>.db`
  - 상점 정보, 사용자, 상품, 구매로그, 충전로그, 충전신청, 감사로그 등

---

## 3. 사용자 시나리오

### A. 관리자

1. 디스코드에서 서버 등록
2. 웹패널(`/login`) 로그인
3. 기본설정에서 상점 정보(이름/로고/공개여부/계좌) 설정
4. 제품관리에서 상품 등록
5. 유저관리/충전신청관리/라이센스관리 운영

### B. 상점 사용자

1. `/<server_id>/login` 또는 `/<server_id>/signup` 접속
2. 회원가입/로그인
3. 상품 목록에서 구매
4. 잔액 부족 시 충전신청
5. 승인 후 잔액 증가, 구매 가능

---

## 4. 핵심 알고리즘 (중요)

## 4-1. 구매 알고리즘

라우트: `POST /<server_id>/buy`

1. 로그인/차단 여부 확인
2. 상품/수량 검증
3. 잔액 검증
4. 재고(문자열 라인 단위)에서 수량만큼 차감
5. 잔액 차감
6. 구매로그 기록
7. 주문코드(7자리 랜덤 숫자) 생성 후 전달 테이블 저장
8. 성공 시 주문 상세 URL 반환

### 동시성 보호

- `BEGIN IMMEDIATE` 트랜잭션으로 구매 중 write lock 선점
- 재고/잔액/로그를 **원자적(한 번에)** 처리
- 실패 시 롤백

---

## 4-2. 충전신청/승인 알고리즘

### 수동 승인

라우트: `/managereq` (`accept`)

1. 충전신청 행 조회
2. 유저 잔액 증가
3. 충전로그 기록
4. 충전신청 삭제

### 자동 승인(OCR)

1. 사용자가 충전신청 생성
2. 관리자 설정에서 자동승인 ON이면 백그라운드 워커 큐로 전달
3. OCR로 영수증 텍스트 추출
4. 검증:
   - 시간(현재 기준 5분 이내)
   - 입금계좌 번호 일치
5. 통과 시 자동 승인 처리

### 악용 방지

- 이미지 해시 + OCR 지문(फingerprint) 저장
- 과거 승인 데이터와 중복이면 자동승인 거부

---

## 4-3. 감사로그 알고리즘

테이블: `admin_audit_log`

- 관리자 주요 변경 작업마다:
  - 누가(`admin_id`)
  - 언제(`created_at`)
  - 무엇을(`action`, `target`)
  - 변경 전/후(`before_json`, `after_json`)
  - IP(`ip`)
  를 기록합니다.

운영 중 문제 발생 시 “누가 어떤 값을 바꿨는지” 추적 가능합니다.

---

## 5. 주요 URL

### 관리자

- `/login` : 관리자 로그인
- `/setting` : 기본 설정 + KPI
- `/manage_user` : 유저 관리
- `/manage_product` : 제품 관리
- `/managereq` : 충전 신청 관리
- `/license` : 라이센스 관리
- `/audit_log` : 감사로그

### 상점 사용자

- `/<server_id>/login` : 로그인
- `/<server_id>/signup` : 회원가입
- `/<server_id>` : 상품 목록
- `/<server_id>/charge` : 충전신청
- `/<server_id>/charge-history` : 충전내역
- `/<server_id>/orders` : 구매내역
- `/<server_id>/<order_code>` : 주문 상세

---

## 6. 실행 방법 (처음 설치)

## 6-1. 가상환경/의존성

```powershell
cd "C:\Users\koyto\OneDrive\바탕 화면\Venex-main"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 6-2. `config.py` 생성 (로컬 전용)

```python
token = "디스코드_봇_토큰"
GUILD_ID = 123456789012345678
```

## 6-3. 웹 실행

```powershell
$env:VENEX_SECRET_KEY="랜덤긴문자열"
$env:VENEX_HOST="0.0.0.0"
$env:VENEX_PORT="5000"
python web.py
```

## 6-4. 봇 실행

```powershell
python app.py
```

---

## 7. 백업/복구

- 백업:
```powershell
python scripts/backup_db.py --db-dir db --out-dir backups
```

- 최신 백업 복구:
```powershell
python scripts/restore_db.py --db-dir db --backup-root backups --source latest
```

복구 전 현재 DB는 자동 안전백업됩니다.

---

## 8. 운영 관점 체크포인트

1. `config.py`, 토큰, 비밀키는 절대 Git에 올리지 않기
2. HTTPS + reverse proxy(Nginx) 적용
3. 매일 DB 백업 자동화
4. 테스트(`pytest`) 정기 실행
5. 관리자 비밀번호/세션 보안 강화(권장: 해시 저장)

---

## 9. 한눈에 이해하는 흐름

1. 서버 등록 → 서버별 DB 생성  
2. 관리자 설정 → 상점 공개/상품 등록  
3. 사용자 가입/로그인 → 구매 또는 충전신청  
4. 충전 승인(수동/자동 OCR) → 잔액 증가  
5. 구매 처리 → 재고 차감 + 주문 생성 + 로그 기록  
6. 모든 관리자 변경은 감사로그에 남음

