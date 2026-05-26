# Basic Software Technology

**Ollama** 기반 로컬 LLM 들과 대화하고, 채팅을 통해 엑셀 작업이 가능하며, 필요 시 Python 코드를 **승인 후 실행**하는 Streamlit 앱입니다.

| 항목 | 내용 |
|------|------|
| UI 프레임워크 | Streamlit (**AI 채팅** · **Ollama 관리** 가능) |
| LLM | Ollama 로 실행하는 로컬 LLM 모델 `POST /api/chat` |
| 진입점 | `app.py` |
| 기본 URL | `http://localhost:8507` |

- [시스템의 구성요소](#시스템의-구성요소)
- [LLM 실행 구조](#llm-실행-구조)
- [사용 화면 캡쳐](#사용-화면-캡쳐)

---

## 시스템의 구성요소

이 저장소는 Streamlit 기반 **단일 앱 파일(`app.py`)** 중심입니다. React·별도 프론트·랜딩 HTML은 없습니다.

### 저장소 구조

```
basic-sw-tech-sm/
├── app.py                    # UI · Ollama · 파일 · 코드 실행 (전부 여기)
├── requirements.txt          # Python 패키지
├── .streamlit/config.toml    # Streamlit 서버 설정 (포트 8507)
├── chat_history/             # 실행 중 생성 (대화·프로필·workspace)
└── README.md
```

| 파일 / 폴더 | 역할 |
|-------------|------|
| `app.py` | `main()` → 사이드바 설정 + 메인 채팅 루프 |
| `.streamlit/config.toml` | 포트 `8507`, headless 모드 |
| `chat_history/index.json` | 대화 목록·메시지 영속 저장 |
| `chat_history/user_profile.json` | 이름·언어·시간대 등 (선택 입력) |
| `chat_history/app_settings.json` | Persona 선택·커스텀 Persona |
| `chat_history/workspaces/{id}/` | 첨부 파일·코드 실행 결과 파일 |

### 앱 화면 구조 (Streamlit)

```mermaid
flowchart LR
    subgraph Browser["브라우저"]
        Page["단일 페이지<br/>채팅 + 사이드바"]
    end

    subgraph App["app.py"]
        direction TB

        Nav["사이드바 네비<br/>AI 채팅 · Ollama 관리"]
        Side["채팅 사이드바<br/>Ollama · Persona<br/>프로필 · 히스토리"]
        Main["메인<br/>대화 목록 + chat_input"]

        Nav --- Side
        Side --- Main
    end

    Page --> App
```

| 영역 | 담당 기능 |
|------|-----------|
| **메인** | 메시지 표시, 파일 첨부 입력, 코드 승인·실행 결과 |
| **사이드바** | Ollama URL·모델, 시스템 프롬프트(Persona), 유저 프로필, 대화 관리·보내기 |

### 실행 방법

매우 간단합니다.

```powershell
pip install -r requirements.txt
streamlit run app.py          # .streamlit/config.toml → 포트 8507 (수정 가능)
```

> LLM이 생성한 코드는 승인 후 `workspaces/{대화ID}/_run_script.py`로 **임시 실행**됩니다. 이 파일은 앱을 띄우는 스크립트와 무관합니다.

---

## LLM 실행 구조

한 번 메시지를 보낼 때: **입력 처리 → `messages` 조립 → Ollama 1회 호출 → (조건 시) 코드 승인 실행**. 스트리밍 없음 (`stream: false`).

### 한눈에 보기

```mermaid
flowchart LR
    A[입력] --> B[컨텍스트]
    B --> C[Ollama]
    C --> D[응답]
    D --> E{코드?}
    E -->|Yes| F[승인 실행]
    E -->|No| G[저장]
    F --> G
```

### `system` 메시지 조립

```mermaid
flowchart TB
    subgraph SYS["system (1개로 합침)"]
        direction TB
        P[Persona]
        U[유저 프로필]
        D[활성 데이터셋]
        F[첨부 시: 코드 지시 + 파일 경로]
    end

    H[user / assistant 히스토리] --> MSG[messages]
    SYS --> MSG
    MSG --> API[Ollama /api/chat]
```

| system 블록 | 설정 위치 |
|-------------|-----------|
| Persona | 사이드바 · Preset 3종 + Custom (`app_settings.json`) |
| 프로필 | 모달 · `user_profile.json` |
| 데이터셋 | `st.session_state.df` 요약 |
| 첨부 지시 | 파일 있을 때만 · workspace 경로 포함 |


### 파일 첨부 · 코드 실행 구조

파일이 있거나 활성 데이터셋(`df`)이 있으면, 모델이 ` ```python ` 블록을 내면 **자동 실행하지 않고** 승인 UI를 띄웁니다. 아래 시퀀스는 **승인 이후 workspace 실행** 단계를 시간 순으로 보여 줍니다.

```mermaid
sequenceDiagram
    participant U as 사용자
    participant S as Streamlit
    participant O as Ollama
    participant W as Workspace

    U->>S: 메시지 + 파일
    S->>W: 첨부 파일 저장
    S->>O: messages (파일 요약 + 경로 + CODE_AGENT_INSTRUCTION)
    O-->>S: 답변 (+ python 블록)
    S->>U: 실행 코드 표시 / 승인·취소

    alt 실행 승인
        U->>S: ✅ 실행 승인
        S->>W: _run_script.py 작성 후 subprocess 실행
        W-->>S: 실행 결과 / 상세 기록, 신규 파일 목록
        S->>U: 실행 로그 + 생성 파일 다운로드
    else 실행 취소
        U->>S: ❌ 실행 취소
    end
```

| 단계 | 함수 | 설명 |
|------|------|------|
| 작업 폴더 | `get_chat_workspace()` | `chat_history/workspaces/{active_chat_id}/` |
| 실행 | `execute_python_code()` | `sys.executable`로 스크립트 실행, cwd=workspace, 타임아웃 120초 |
| 신규 파일 | `list_workspace_files()` diff | 실행 전후 파일 비교 → 다운로드 버튼 |
| 상태 저장 | `patch_message()` | `execution_status`, `execution_result` 메시지에 기록 |

**실행 상태 (`execution_status`):**

- `pending` — 승인 대기
- `completed` — 실행 완료 (결과·다운로드 표시)
- `cancelled` — 사용자 취소

---

## 사용 화면 캡쳐

### 요청 의도별 코드 생성

사용자의 승인을 받아 실행 후에 생성된 파일을 받을 수 있습니다.

<img width="1997" height="1891" alt="코드 실행 승인 및 결과 파일 다운로드" src="https://github.com/user-attachments/assets/9cf8313c-3b0f-4050-b84f-be0ed319ce8d" />

### 시스템 프롬프팅 페르소나화

프리셋 페르소나 외 사용자가 생성 및 관리할 수 있습니다.

<img width="1997" height="1687" alt="Persona 프리셋 및 커스텀 관리" src="https://github.com/user-attachments/assets/b6470f32-29fd-4125-b9f7-46f85bb812bc" />

### Ollama 관리

SSH 터널로 원격 Ollama에 연결한 뒤, 모델 목록 확인·`pull` 다운로드·삭제를 할 수 있습니다.

<img width="1997" height="1891" alt="오라마 관리" src="https://github.com/user-attachments/assets/ff921a78-2f98-46d2-994b-244ac426d21e" />
