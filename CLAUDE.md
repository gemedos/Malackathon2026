<<<<<<< Updated upstream

1. Solución implementada para Pragmatic Play debe ser extensible a otros proveedores.

Flujo:

1. Entro en www.betson.com
2. Scroll hasta de sección proveedores.
3. Clic Pragmatic Play.
4. Entrar en juego.
5. Configurar sesión: cada vez que entres a una plataforma debes especificar cuánto tiempo vas a jugar y qué dinero quieres gastar.
6. Testear botones apuestas.
7. # Funciona? Acceso a saldo

# PROJECTS.md — Intelligent Game Validation

## 1. Project Overview

- **Project:** Malackathon 2026 — Intelligent Game Validation
- **Client:** Betsson Group
- **Objective:** Build an automated testing system that validates third-party casino games from the player's perspective.
- **Main challenge:** Interact with and validate casino games without accessing their internal DOM.
- **Target provider:** Pragmatic Play.
- **Target platform:** Betsson casino.
- **Expected result:** A working proof of concept that automatically executes casino game tests, validates their outcomes, and generates evidence-based reports.

### Core principle

- The system must verify what the player actually sees.
- Clicking a button does not constitute successful validation.
- The system must observe and verify the game's response.
- Tests must work even when game interfaces are rendered inside iframes or canvases.
- Computer vision, OCR, image recognition, and AI are permitted but not mandatory.
- The technology and architecture are freely selectable.

---

## 2. Functional Requirements

### FR-01 — Market Configuration

- [ ] Support two casino markets:
  - `betsson.com`
    - Language: English
    - Currency: EUR
  - `betsson.pe`
    - Language: Spanish
    - Currency: PEN
- [ ] Allow market configuration without modifying test logic.
- [ ] Validate the displayed currency against the selected market.
- [ ] Validate the expected language for relevant messages.
- [ ] Execute both testing scenarios independently for each market.

### FR-02 — Authentication

- [ ] Navigate to the correct Betsson casino lobby.
- [ ] Authenticate using the provided test accounts.
- [ ] Support funded accounts for successful-spin testing.
- [ ] Support accounts without sufficient funds for rejection testing.
- [ ] Never hard-code credentials.
- [ ] Never expose credentials in logs, screenshots, reports, recordings, or GitHub.

### FR-03 — Game Navigation

- [ ] Navigate through the casino lobby.
- [ ] Locate an available Pragmatic Play game.
- [ ] Launch the selected game.
- [ ] Enter **Real Play** mode.
- [ ] Confirm that the game has loaded successfully.
- [ ] Detect when the game is ready for interaction.
- [ ] Support games rendered inside iframes or canvases.
- [ ] Do not depend on access to the game's internal DOM.

### FR-04 — Visual Interaction

- [ ] Identify relevant game controls using visible information.
- [ ] Locate the Spin button.
- [ ] Read the displayed wager.
- [ ] Read the displayed currency.
- [ ] Read the displayed in-game balance.
- [ ] Read the Betsson account balance.
- [ ] Detect visible game state changes.
- [ ] Detect when a spin starts.
- [ ] Detect when a spin finishes.
- [ ] Read the visible spin outcome.
- [ ] Detect insufficient-balance messages.
- [ ] Verify results from visual evidence rather than assuming success after interaction.

---

## 3. Testing Scenarios

### SC-01 — Completed Real Play Spin

**Objective:** Verify that a real-money spin completes correctly and that balances reconcile.

#### Execution

- [ ] Open the casino lobby for the selected market.
- [ ] Authenticate with a funded test account.
- [ ] Launch an available Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read the Betsson balance before spinning.
- [ ] Read the in-game balance before spinning.
- [ ] Identify the displayed wager.
- [ ] Identify the displayed currency.
- [ ] Locate the Spin control.
- [ ] Trigger one spin.
- [ ] Verify visually that the spin started.
- [ ] Wait until the spin has completed.
- [ ] Verify visually that the spin finished.
- [ ] Read the settled outcome.
- [ ] Determine the payout from the observed outcome.
- [ ] Read the in-game balance after the spin.
- [ ] Read the Betsson balance after the spin.

#### Validation

- [ ] The spin started successfully.
- [ ] The spin completed successfully.
- [ ] The wager used matches the displayed wager.
- [ ] The displayed currency matches the selected market.
- [ ] The in-game balance is consistent with the completed spin.
- [ ] The Betsson balance reconciles with the wager and payout.

#### Balance Formula

```text
Expected balance after = Balance before - Wager + Payout
```

Validation:

```text
Actual balance after == Expected balance after
```

- A losing spin is valid.
- A winning spin is valid.
- The payout must be determined from the visible completed outcome.
- The test passes only when the observed balances are consistent with the completed spin.

---

### SC-02 — Insufficient Balance

**Objective:** Verify that a spin is rejected when the player has insufficient funds.

#### Execution

- [ ] Open the casino lobby for the selected market.
- [ ] Authenticate with the supplied insufficient-balance account.
- [ ] Launch an available Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read the Betsson balance before attempting the spin.
- [ ] Read the in-game balance before attempting the spin.
- [ ] Identify the displayed currency.
- [ ] Attempt a spin.
- [ ] Observe the game's response.
- [ ] Detect the insufficient-balance message.
- [ ] Read the Betsson balance after the attempt.
- [ ] Read the in-game balance after the attempt.

#### Validation

- [ ] The spin is rejected.
- [ ] No paid spin completes.
- [ ] An insufficient-balance message appears.
- [ ] The message is displayed in the expected language.
- [ ] The displayed currency matches the selected market.
- [ ] The Betsson balance remains unchanged.
- [ ] The in-game balance remains unchanged.

#### Expected Language

**English market:**

- Detect an appropriate insufficient-balance message in English.

**Peruvian market:**

- Detect an appropriate insufficient-balance message in Spanish.

The exact message text is not specified by the challenge and should not be assumed.

---

## 4. Test Matrix

The application must execute four test combinations.

| Test ID | Market      | Scenario             | Currency |
| ------- | ----------- | -------------------- | -------- |
| T01     | betsson.com | Completed Spin       | EUR      |
| T02     | betsson.com | Insufficient Balance | EUR      |
| T03     | betsson.pe  | Completed Spin       | PEN      |
| T04     | betsson.pe  | Insufficient Balance | PEN      |

### Requirements

- [ ] Execute all four combinations.
- [ ] Generate independent results for each combination.
- [ ] Identify every result by market and scenario.
- [ ] Include all required balance validations.
- [ ] Provide evidence supporting each test result.

---

## 5. Technical Requirements

The challenge does not prescribe a specific technology stack.

The following are **recommended implementation requirements**, not mandatory competition rules.

### TR-01 — Browser Automation

- [ ] Automate browser navigation.
- [ ] Support authentication.
- [ ] Support navigation through the casino lobby.
- [ ] Support launching third-party games.
- [ ] Capture screenshots during execution.
- [ ] Handle asynchronous game loading.

**Recommended technology:** Playwright.

### TR-02 — Computer Vision

- [ ] Capture screenshots of the game interface.
- [ ] Identify relevant visual elements.
- [ ] Locate interactive controls.
- [ ] Recognize game state changes.
- [ ] Detect visible messages.
- [ ] Extract displayed balances and wagers.

**Possible technologies:**

- OpenCV
- OCR
- Vision-language models
- Image recognition

Do not require all these technologies. Choose the simplest reliable approach.

### TR-03 — State Detection

- [ ] Identify when the game is loading.
- [ ] Identify when the game is ready.
- [ ] Identify when a spin starts.
- [ ] Identify when a spin completes.
- [ ] Identify when an error message appears.
- [ ] Avoid interpreting a successful click as a successful test.

### TR-04 — Balance Validation

- [ ] Extract monetary values from the visible interface.
- [ ] Identify the wager.
- [ ] Identify the payout.
- [ ] Calculate the expected final balance.
- [ ] Compare the expected balance against the observed balance.
- [ ] Validate both Betsson and in-game balances.
- [ ] Handle EUR and PEN.
- [ ] Use decimal-safe monetary calculations rather than floating-point equality.

### TR-05 — Reliability

- [ ] Wait for observable state changes instead of relying exclusively on fixed delays.
- [ ] Handle loading failures.
- [ ] Handle missing visual elements.
- [ ] Handle unexpected dialogs.
- [ ] Distinguish test failures from execution errors.
- [ ] Avoid reporting PASS when the result cannot be verified.

---

## 6. Reporting Requirements

### RR-01 — Test Results

- [ ] Generate a report after test execution.
- [ ] Identify the market.
- [ ] Identify the scenario.
- [ ] Display PASS/FAIL for every required validation.
- [ ] Include Betsson balance checks.
- [ ] Provide supporting visual evidence.

### RR-02 — Evidence

- [ ] Capture screenshots or equivalent visual evidence.
- [ ] Capture evidence of the initial game state.
- [ ] Capture evidence of the completed spin.
- [ ] Capture evidence of the resulting balances.
- [ ] Capture evidence of insufficient-balance rejection.
- [ ] Capture evidence of the unchanged balances.

### RR-03 — Recommended Report Format

```text
TEST REPORT

Market: betsson.com
Language: English
Currency: EUR

Scenario: Completed Real Play Spin

Game launched: PASS
Real Play activated: PASS
Initial balance detected: PASS
Wager detected: PASS
Spin started: PASS
Spin completed: PASS
Payout detected: PASS
Currency validated: PASS
In-game balance validated: PASS
Betsson balance validated: PASS

FINAL RESULT: PASS
```

This is an illustrative report format, not an actual test result.

---

## 7. GitHub Requirements

### GR-01 — Repository

- [ ] Store the source code in a GitHub repository.
- [ ] Organize the project clearly.
- [ ] Separate market configuration from test logic.
- [ ] Include the necessary dependencies.
- [ ] Include instructions for running the tests.
- [ ] Exclude credentials and secrets.

### GR-02 — GitHub Actions

- [ ] Create a GitHub Actions workflow.
- [ ] Execute the completed-spin scenario for both markets.
- [ ] Execute the insufficient-balance scenario for both markets.
- [ ] Run each scenario once per market.
- [ ] Generate the test report.
- [ ] Publish the report as a workflow artifact.
- [ ] Make supporting evidence accessible.

---

## 8. Security Requirements

- [ ] Use only the supplied test accounts.
- [ ] Obtain test credentials from Betsson.
- [ ] Coordinate with mentors to prepare insufficient-balance accounts.
- [ ] Never commit credentials.
- [ ] Never expose authentication secrets.
- [ ] Never include credentials in screenshots or recordings.
- [ ] Never include secrets in presentations or reports.
- [ ] Use the correct market configuration.

---

## 9. Deliverables

### D-01 — Source Code

- [ ] Working automated testing application.
- [ ] Public or accessible GitHub repository.
- [ ] Clear project structure.
- [ ] Market configuration.
- [ ] No committed credentials.

### D-02 — GitHub Actions

- [ ] Working CI workflow.
- [ ] Four test combinations executed.
- [ ] Published report.

### D-03 — Report and Evidence

- [ ] PASS/FAIL results for each check.
- [ ] Results identified by market and scenario.
- [ ] Betsson balance verification.
- [ ] Screenshots, trace, or video.

### D-04 — Presentation (Finalists Only)

- [ ] Prepare a seven-minute presentation.
- [ ] Demonstrate a working execution.
- [ ] Explain the architecture.
- [ ] Explain the technical decisions.
- [ ] Show how the system validates visible outcomes.

---

## 10. Evaluation Criteria

| Criterion                               |  Points |
| --------------------------------------- | ------: |
| Both scenarios work on both markets     |      30 |
| Validates the visible player experience |      20 |
| Code quality and architecture           |      15 |
| Reports and supporting evidence         |      15 |
| GitHub Actions integration              |      10 |
| Working demonstration                   |      10 |
| **Total**                               | **100** |
| Bonus                                   |     +10 |

**Maximum possible score: 110 points.**

The highest-priority requirements are successful execution of all four test combinations and reliable validation of visible game behavior.

---

## 11. Development Priorities

The following order is my recommendation for implementing the project during the hackathon.

### P0 — Essential

- [ ] Browser navigation.
- [ ] Authentication.
- [ ] Launch Pragmatic Play game.
- [ ] Enter Real Play.
- [ ] Read balances and wager.
- [ ] Execute a spin.
- [ ] Verify spin completion visually.
- [ ] Validate balance reconciliation.
- [ ] Detect insufficient-balance rejection.
- [ ] Run both scenarios on both markets.

### P1 — Required Deliverables

- [ ] Automated PASS/FAIL reporting.
- [ ] Screenshots or equivalent evidence.
- [ ] GitHub Actions execution.
- [ ] Published reports.
- [ ] Secure credential handling.

### P2 — Improvements

- [ ] More robust computer vision.
- [ ] Improved error recovery.
- [ ] Better visual reporting.
- [ ] Additional supported games.
- [ ] Improved test reliability.

These improvements are optional and should not delay the mandatory functionality.

---

## 12. Definition of Done

The project is complete when:

- [ ] The application successfully authenticates on both markets.
- [ ] It launches an available Pragmatic Play game in Real Play.
- [ ] It validates a completed spin using visible evidence.
- [ ] It validates the Betsson and in-game balances.
- [ ] It correctly identifies insufficient-balance rejection.
- [ ] It verifies that balances remain unchanged after rejection.
- [ ] It produces results for all four market/scenario combinations.
- [ ] It generates a report with PASS/FAIL checks and supporting evidence.
- [ ] GitHub Actions executes the required tests and publishes the report.
- [ ] No credentials or secrets are exposed.

---

### Important architectural recommendation

**Don't start by building an autonomous AI agent.**

The challenge rewards reliable visual verification, not AI complexity.

For this hackathon, I would use:

**Playwright → Screenshots → Visual Recognition → State Validation → Reports → GitHub Actions**

This architecture directly addresses the challenge while keeping implementation manageable within the available development window.

The official brief gives **30 points for working scenarios and 20 for player-visible validation**. Together, these represent 50% of the base score. Prioritize those capabilities before adding advanced features.

> > > > > > > Stashed changes
