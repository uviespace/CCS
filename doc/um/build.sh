#!/bin/bash


./cleanup.sh

xelatex ccs_um.tex

makeglossaries ccs_um

biber ccs_um

xelatex ccs_um.tex

xelatex ccs_um.tex

mv ccs_um.pdf "UVIE-CCS-UM-r1.pdf"


