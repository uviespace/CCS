#!/bin/bash


./cleanup.sh

xelatex ccs_um.tex

makeglossaries ccs_um

biber ccs_um

xelatex ccs_um.tex

xelatex ccs_um.tex

mv ccs_um.pdf "HB-UVIE-EGSE-UM-001_i1.0.pdf"


