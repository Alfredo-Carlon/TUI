# TUI
A library to create textual user interfaces developed by Claude


## Description
This is a standalone Python library created entirely by Claude after an iteration of 15 rounds.
It contains no formal tests, the testing technique was 'vibe-coding': I'll use it and if it
works then move on, if not, make Claude aware of it.

The goal of this library is writing tuis quickly without any 3rd party dependency.
The file `tui/creator.py` reads a specification file that describes a tui and 
outputs a python program implementing it. The example file `tui/spec_example.spec`
should contain all the information an agent needs to create an specification file
to be used with `tui/creator.py` this should reduce token use :)
