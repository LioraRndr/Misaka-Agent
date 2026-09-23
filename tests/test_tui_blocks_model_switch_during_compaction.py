"""A model or thinking-level switch during a compaction voids the compaction when it lands
(`_check_compaction_source` sees the model and the appended entries changed). With LCM a
compaction can take minutes; on 2026-09-24 a Sister at 1.19M tokens lost a five-minute one to
three `/model` presses and overflowed. The three switch entry points now wait, as `/reload`
already does; an idle session is unchanged."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from misaka.ui.tui.interactive.interactive_mode import InteractiveMode


def _mode(compacting):
    mode = InteractiveMode.__new__(InteractiveMode)
    warnings, selector = [], []
    mode.session = SimpleNamespace(isCompacting=compacting, cycleModel=AsyncMock(return_value=None),
                                   scopedModels=[])
    mode.showWarning = warnings.append
    mode.showStatus = lambda text: None
    mode.showError = lambda text: None
    mode.showModelSelector = lambda *args, **kwargs: selector.append(args)
    return mode, warnings, selector


async def test_every_switch_waits_while_compacting():
    mode, warnings, selector = _mode(compacting=True)
    await mode.handleModelCommand(None)
    await mode._cycle_model("next")
    mode.handleThinkingCommand("high")
    assert len(warnings) == 3 and all("compaction" in text for text in warnings)
    assert selector == [] and not mode.session.cycleModel.await_count


@pytest.mark.parametrize("entry", ["command", "cycle"])
async def test_an_idle_session_switches_as_before(entry):
    mode, warnings, selector = _mode(compacting=False)
    if entry == "command":
        await mode.handleModelCommand(None)
        assert selector == [()]
    else:
        await mode._cycle_model("next")
        assert mode.session.cycleModel.await_count == 1
    assert warnings == []
