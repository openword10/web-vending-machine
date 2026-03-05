# VENDIX Shop System Briefing

## 1. 목적
- 관리자 웹패널에서 상점 공개 여부와 기본 운영값을 설정한다.
- 상점 주소는 `서버 ID`로 고정된다.
- 공개 상점에서 사용자 회원가입/로그인을 한 뒤 제품 목록을 조회한다.

## 2. 핵심 구조
- 백엔드: `Flask` (`web.py`)
- 데이터베이스: `SQLite` (`db/<server_id>.db`)
- 관리자 인증 세션: `session["id"]`
- 상점 사용자 세션: `session["shop_user_<server_id>"]`

## 3. 라우팅 알고리즘
### 3.1 관리자 패널
- `GET /login`: 관리자 로그인 페이지 렌더링.
- `POST /login`: 서버 ID + 패스워드 검증 후 `session["id"]` 저장.
- `GET /setting`: 관리자 설정 페이지 렌더링.
- `POST /setting`: 설정값 저장.
  - 서버 ID는 수정하지 않음.
  - `shop_public`은 `0/1`만 허용.
  - 상점 주소(`shop.slug`)는 항상 현재 `session["id"]`로 저장.

### 3.2 공개 상점
- `GET /<server_id>`:
  - `server_id`가 숫자인지 확인.
  - 해당 DB 존재 여부 확인.
  - 상점 공개 여부(`shop.is_public`)가 1인지 확인.
  - 로그인 세션(`shop_user_<server_id>`)이 있으면 제품 목록 조회.
  - 없으면 로그인/회원가입 UI만 표시.
- `POST /<server_id>/auth/signup`:
  - 입력값(ID/PW/디스코드 ID/GMAIL) 필수 검증.
  - 상점별 `shop_member` 테이블에 사용자 생성.
  - 생성 성공 시 상점 사용자 세션 발급.
- `POST /<server_id>/auth/signin`:
  - ID/PW 검증 후 상점 사용자 세션 발급.
- `GET /<server_id>/auth/logout`:
  - 상점 사용자 세션 삭제 후 상점 페이지로 리다이렉트.

## 4. DB 스키마 설계
### 4.1 기존 상점 테이블
- `shop(name, slug, description, logo_url, banner_url, theme_color, is_public)`
- 현재 운영 규칙:
  - `slug`는 서버 ID로 고정.
  - `is_public` 기본값은 `0`(비공개).

### 4.2 신규 상점 회원 테이블
- `shop_member(id PRIMARY KEY, password, discord_id, gmail, created_at)`
- 서버별 DB에 존재하므로, 계정 범위는 상점 단위로 분리됨.

## 5. 프론트 변경 사항
- 화이트 모드 고정: `static/js/vendix-theme.js`
- 관리자 설정(`templates/manage.html`)
  - 상점 주소 입력 제거, 서버 ID 읽기 전용 표시.
  - 상점소개/로고/배너/대표색상 입력 제거.
  - 공개여부 필드 유지.
  - 공개여부 `0 -> 1` 전환 시 확인 팝업.
  - `샵웹사이트 가기` 버튼 추가.
  - 입력창 글자색 강제(어두운 글자)로 가독성 보정.
- 제품 관리(`templates/manage_prod.html`)
  - `제품추가하기` 버튼 추가 (`/createprod` 이동).
- 공개 상점(`templates/shop_public.html`)
  - 상점 로그인/회원가입 폼 제공.
  - 로그인 이후 제품 목록 표시.

## 6. 동작 순서(운영 플로우)
1. 디스코드 봇/라이선스로 서버 DB 생성.
2. 관리자 로그인 후 `/setting`에서 상점 공개여부 설정.
3. 공개가 1이면 `/<서버ID>` 주소로 상점 접근 가능.
4. 사용자는 해당 상점에서 회원가입/로그인.
5. 로그인된 사용자만 제품 목록 조회.
6. 관리자는 `/manage_product` 및 `/createprod`에서 제품 관리.

## 7. 운영 체크리스트
- `db/<server_id>.db` 파일 존재 확인.
- 관리자 계정으로 `/setting` 저장 정상 여부 확인.
- 공개여부 0/1 전환 및 확인 팝업 동작 확인.
- `/<server_id>` 접속 시 비로그인/로그인 화면 분기 확인.
- 회원가입 중복 ID 검증 확인.
- 제품 추가 후 상점 사용자 로그인 상태에서 목록 노출 확인.
