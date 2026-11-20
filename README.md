# software-architecture

[한국어](README.ko.md)

A Codex skill for deciding how software should be put together. Start with one task a user needs to complete. Trace it from input to result to see who makes each decision, where the data lives, and what happens if a step fails.

**[Download software-architecture](https://github.com/Ddrubok/software-architecture/releases/latest/download/software-architecture.zip)** and extract its folder into `$CODEX_HOME/skills` (default `~/.codex/skills`). The general skill can fetch a specialist when a design decision calls for it.

![An appointment request shows how to assign responsibility, choose a specialist when needed, and decide what to test.](assets/design-flow.en.png)

## Try it with just the general skill

```text
$software-architecture Design the booking flow for a Flutter app with a Rust API.
Two people can tap the same time slot. Who confirms the booking? What does each screen show?
```

Codex identifies two decisions in this request. The Flutter specialist handles the screen state while the request is in progress. The Rust specialist helps place the write that accepts or rejects the booking. Together they produce one testable rule: two simultaneous requests for one slot yield one confirmed booking.

When Codex selects a specialist, it first looks for a local copy. If it is missing, the included Python 3 helper downloads the listed GitHub release, checks its SHA-256 digest, and installs it in your skills directory. Codex then reads it during the same task. If you ask to work offline, Codex uses the skills already available. A general design question can be answered with the base skill alone.

## Which version did my design use?

The design reports each specialist it actually read. The helper checks the local files against published ZIP inventories, including older releases. To inspect a particular copy offline, run this command from the general skill folder. Replace the final path with that copy's actual location.

```sh
python3 scripts/ensure_specialist.py godot-game-architecture --status --entry "/path/to/godot-game-architecture/SKILL.md"
```

Add `--json` for structured output. A verified tag identifies matching release files. A local edit can still be traced to the original download when an install record exists. A VERSION file on its own identifies what the copy declares. Inspection preserves local files.

## Available specialists

| Technology | A decision the skill helps make |
| --- | --- |
| [Unity](https://github.com/Ddrubok/unity-game-architecture) | Which part owns the run when a scene changes? |
| [Godot](https://github.com/Ddrubok/godot-game-architecture) | Which state belongs to the room, and which must survive leaving it? |
| [Unreal Engine](https://github.com/Ddrubok/unreal-game-architecture) | Who confirms a score, and what survives a Pawn respawn? |
| [Flutter](https://github.com/Ddrubok/flutter-app-architecture) | What happens to a pending save when the user leaves the screen? |
| [Rust](https://github.com/Ddrubok/rust-software-architecture) | Which code needs a crate boundary, and who handles a failed write? |

Each specialist is also available on its own. For computers you plan to use offline, you can still preinstall Unity with the [general + Unity ZIP](https://github.com/Ddrubok/software-architecture/releases/latest/download/software-architecture-with-unity.zip).

## What you get

- A map of the components involved in the first user task and how they communicate
- A decision about who can change each piece of data and how long it is kept
- Checks for the normal flow and relevant failures, plus the conditions that would change the design

Ask for implementation as well, and Codex follows the design through the first working flow in the project. [Skill instructions](SKILL.md) · [Specialist selection and installation](references/domain-routing.md)
