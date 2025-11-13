#!/bin/bash

xelatex usermanual.tex --shell-escape

makeglossaries usermanual

biber usermanual

xelatex usermanual.tex

xelatex usermanual.tex

mv usermanual.pdf HB-UVIE-EGSE-UM-001_i1.0.pdf

./cleanup.sh

