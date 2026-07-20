"""PySide6/Qt desktop shell — a thin consumer of the sim core.

Everything under ``arda_sim.ui`` imports PySide6; the sim core does not, so the
core and its tests never depend on Qt. Install the UI extra to run it:

    pip install -e ".[ui]"
    arda-sim-ui
"""
