[33mcommit 7ea395d824f9d923da35d0f92c08bc0f977d4a0b[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mplaywright_vision[m[33m)[m
Author: Deniz Inan <68498418+DenoFury@users.noreply.github.com>
Date:   Thu Oct 15 16:41:44 2026 +0200

    Updated version

 .gitignore                                |   9 [32m++++++[m
 config/games/pragmatic-play/_default.yaml |  31 [32m++++++++++++++++++[m
 config/games/pragmatic-play/spin.png      | Bin [31m0[m -> [32m18552[m bytes
 config/games/pragmatic-play/splash.png    | Bin [31m0[m -> [32m19873[m bytes
 config/selectors/es.yaml                  |  34 [32m+++++++++++++++++[m[31m---[m
 docs/MAPA.md                              |  22 [32m+++++++++++++[m
 ignore/transcript betsson.txt             |   0
 src/validator/browser.py                  |  40 [32m+++++++++++++++++++++[m[31m--[m
 src/validator/config.py                   |  14 [32m++++++++[m
 src/validator/game/account.py             |  29 [32m++++++++++++++[m[31m---[m
 src/validator/game/calibration.py         |  23 [32m++++++++++++++[m
 src/validator/game/scenarios.py           |  41 [32m+++++++++++++++++++++++[m[31m-[m
 src/validator/navigation.py               |   6 [32m++[m[31m--[m
 src/validator/pages/base_page.py          |   7 [32m++[m[31m--[m
 src/validator/pages/game_page.py          |  46 [32m+++++++++++++++++++++++++[m[31m--[m
 tests/fake_slot.py                        |   4 [32m+[m[31m--[m
 tests/test_pregame_offline.py             |  51 [32m++++++++++++++++++++++++++++++[m
 tests/test_provider_calibration.py        |  27 [32m++++++++++++++++[m
 vision-module/vision_engine/evaluation.py |  50 [32m++++++++++++++++++++++++++++[m[31m-[m
 vision-module/vision_engine/ocr.py        |  43 [32m++++++++++++++++++++++++[m[31m-[m
 vision-module/vision_engine/profile.py    |  25 [32m+++++++++++++++[m
 vision-module/vision_engine/scenario.py   |  49 [32m+++++++++++++++++++++++++[m[31m---[m
 22 files changed, 523 insertions(+), 28 deletions(-)
