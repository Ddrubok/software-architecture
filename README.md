# software-architecture

새 기능을 만들기 전에 **어떤 코드가 어떤 책임을 맡을지** 정하는 Codex 스킬입니다. 사용자가 처음 끝내야 할 동작을 하나 고르고, 입력을 받아 결과를 보여주기까지 필요한 모듈과 데이터의 흐름을 설계합니다.

![첫 사용자 동작에서 공통 설계로 이어지고, Unity 구조가 중요할 때 전문 스킬의 결정을 합쳐 실행 흐름과 검증 기준을 정하는 구조도](assets/design-flow.png)

## 어떻게 쓰나요?

Codex에서 스킬 이름과 설계할 프로젝트를 함께 입력합니다.

```text
$software-architecture Unity 게임에 서버 저장을 붙이고 싶어요.
첫 저장이 완료되는 흐름을 기준으로 게임과 서버가 맡을 일을 나눠 주세요.
```

이 요청에서는 플레이어가 **저장 버튼을 누르는 순간**부터 따라갑니다. 서버가 저장 결과를 확정하기로 했다면, 게임은 저장할 정보를 보내고 서버는 쓰기를 완료한 뒤 응답합니다. 저장은 끝났는데 응답만 끊길 수 있으므로, 같은 요청을 다시 받았을 때 어떻게 처리할지도 정합니다.

프로젝트에 `unity-game-architecture` 스킬이 설치돼 있고 씬 전환이 설계에 영향을 준다면, 그 스킬도 읽습니다. 예를 들어 메뉴로 돌아가도 현재 판을 이어갈 수 있어야 한다면, Unity에서 어느 객체가 판의 정보를 계속 갖고 있을지 구체화합니다.

## 무엇을 받나요?

- 첫 동작의 입력부터 결과까지 이어지는 구조와 처리 순서
- 데이터를 바꿀 수 있는 모듈과 그 데이터가 유지되는 기간
- 처음부터 구조에 반영할 요구와, 구조를 다시 검토할 조건
- 정상 작동과 실패 후 복구를 확인할 기준

설계를 요청하면 위 내용을 정리합니다. 구현까지 요청하면 첫 동작이 실제로 실행되도록 연결하고, 그 구조를 선택한 근거가 되는 경로를 확인합니다.

## 설치

Windows PowerShell에서 저장소를 Codex 스킬 폴더에 복제합니다.

```powershell
$skillRoot = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME 'skills'
} else {
    Join-Path $env:USERPROFILE '.codex/skills'
}
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
git clone https://github.com/Ddrubok/software-architecture.git (Join-Path $skillRoot 'software-architecture')
```

[스킬 지침](SKILL.md) · [전문 스킬을 적용하는 조건](references/domain-routing.md)
