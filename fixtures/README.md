# Fixtures

The lab points `setup.py --scan REPO --rules ./rules` at a *sibling*
checkout, never a copy vendored into this repo. The two fixtures
called out by issue [#80](https://github.com/liatrio/ai-code-intelligence/issues/80):

- [`liatrio/gratibot`](https://github.com/liatrio/gratibot) — public
  195-file JavaScript Slack bot. Small, fast to iterate on, and the
  message-text → MongoDB `insertOne` taint chain is already
  documented (CodebaseMemory lab, Wave 6 Prompt 4) so it doubles as a
  frozen oracle for Semgrep's taint mode.
- [`liatrio-labs/liatrio-knowledge`](https://github.com/liatrio-labs/liatrio-knowledge)
  — private, TypeScript-heavy Next.js + Mastra agent stack (5,370 tracked
  files). Only cloneable by Liatrio staff; **never** run this fixture
  with `SEMGREP_APP_TOKEN` set or `semgrep login`, or findings will be
  uploaded to the AppSec Platform.

Clone them **outside** this repository:

```bash
mkdir -p ~/liatrio/repos && cd ~/liatrio/repos
git clone https://github.com/liatrio/gratibot.git
git clone https://github.com/liatrio-labs/liatrio-knowledge.git   # Liatrio staff only
```

Then point `setup.py --scan` at the checkout:

```bash
python3 setup.py --scan ~/liatrio/repos/gratibot          --rules ./rules
python3 setup.py --scan ~/liatrio/repos/liatrio-knowledge --rules ./rules
```

Never commit anything into a fixture checkout. `setup.py` refuses to
scan a fixture that has staged changes on its own branch.
