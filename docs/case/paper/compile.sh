#!/bin/bash
set -e
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode case_paper.tex
bibtex case_paper
pdflatex -interaction=nonstopmode case_paper.tex
pdflatex -interaction=nonstopmode case_paper.tex
echo "PDF: case_paper.pdf"
