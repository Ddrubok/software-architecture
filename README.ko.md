# software-architecture

[English](README.md)

소프트웨어를 어떤 구조로 만들지 정하는 Codex 스킬입니다. 사용자가 처음 완료할 동작 하나를 고르고, 입력부터 결과까지 따라갑니다. 그 과정에서 각 판단을 누가 맡는지, 데이터를 어디에 두는지, 중간에 문제가 생기면 어떻게 처리할지 정합니다.

![예약 요청을 예로 들어 책임을 정하고, 필요할 때 전문 스킬의 도움을 받아 확인 기준을 만드는 구조도](assets/design-flow.png)

## 사용 예시

```text
$software-architecture 예약 앱에서 첫 예약이 완료되는 흐름을 설계해줘.
요청이 어떻게 확정되는지, 두 사람이 같은 시간을 고르면 어떻게 처리하는지 보여줘.
```

누군가 시간을 고르는 순간부터 시작합니다. 시간대 하나에 예약을 하나만 받을 수 있다면, 예약을 최종 확정할 부분을 정합니다. 화면은 그 결과를 표시합니다. 같은 시간에 두 건을 요청하고 정확히 한 건만 확정되는지 확인할 수 있습니다.

## 무엇을 받나요?

- 첫 사용자 동작에 필요한 구성 요소와 서로 정보를 주고받는 방식
- 어떤 구성 요소가 데이터를 바꿀 수 있는지, 그 데이터가 얼마나 오래 유지되는지에 대한 결정
- 정상 경로와 관련 실패 상황의 확인 기준, 구조를 다시 검토할 조건

구현까지 요청하면 Codex가 첫 사용자 흐름을 프로젝트에 연결하고 확인하도록 안내합니다. 플랫폼 제약이 설계에 영향을 주면 설치된 전문 스킬을 해당 부분에 적용할 수 있습니다. [전문 스킬 선택 기준](references/domain-routing.md)

## 설치

저장소를 Codex 스킬 폴더에 복제합니다. Windows PowerShell에서는 아래 명령을 실행합니다.

```powershell
$skillRoot = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $env:USERPROFILE '.codex/skills'
}
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
git clone https://github.com/Ddrubok/software-architecture.git (Join-Path $skillRoot 'software-architecture')
```

[스킬 지침](SKILL.md)
