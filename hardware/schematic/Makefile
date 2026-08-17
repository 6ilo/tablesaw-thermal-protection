# Render the CircuiTikZ sheets to SVG.
#
#   make            build every SVG that is out of date
#   make clean      drop the LaTeX intermediates
#   make distclean  also drop the generated SVGs
#
# Route is  latex -> DVI -> dvisvgm  rather than pdflatex -> PDF,
# because dvisvgm's PDF path needs Ghostscript < 10.01 or mutool,
# while the native DVI path needs neither. --no-fonts traces glyphs
# to paths, so the SVGs carry no font dependency and render
# identically in GitHub, browsers, and Inkscape.

SHEETS := esp32_supervisor ladder_coil_circuit oneline_mains esp32_pictorial
SVGS   := $(addsuffix .svg,$(SHEETS))

LATEX    := latex
DVISVGM  := dvisvgm
LATEXOPT := -interaction=nonstopmode -halt-on-error
SVGOPT   := --no-fonts --exact-bbox --optimize

.PHONY: all clean distclean
all: $(SVGS)

%.svg: %.tex tsstyle.tex
	$(LATEX) $(LATEXOPT) $< > $*.build.log 2>&1 \
	  || { echo "--- $< failed ---"; grep -E '^(!|l\.[0-9]+)' $*.build.log | head -20; exit 1; }
	$(DVISVGM) $(SVGOPT) --output=$@ $*.dvi > /dev/null 2>&1
	@$(MAKE) --no-print-directory clean-one NAME=$*
	@echo "wrote $@"

.PHONY: clean-one
clean-one:
	@rm -f $(NAME).dvi $(NAME).aux $(NAME).log $(NAME).build.log

clean:
	rm -f *.dvi *.aux *.log *.build.log

distclean: clean
	rm -f $(SVGS)
