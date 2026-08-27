# Local parts

The project-specific components nobody ships: the fob, the mains receiver, the
contactor, the optocoupler, the stainless probe. Declarative primitives, rendered by
[`../../../tools/partlib.py`](../../../tools/partlib.py).

These use **the same pin format as the imported Wokwi parts** —
`{name, x, y, signals, description}` — on purpose. The router cannot tell a local
part from an imported one, so a part can be replaced by a better drawing, or by an
upstream one if Wokwi ever ships it, without touching a single netlist.

## Format

```json
{ "id": "optocoupler-dip4", "title": "Optocoupler", "subtitle": "PC817",
  "w": 120, "h": 80,
  "shapes": [ {"t":"rect","x":10,"y":10,"w":100,"h":60,"fill":"#2A2E33","rx":4} ],
  "pins":   [ {"name":"A","x":0,"y":25,"signals":[],"description":"Anode, LED side"} ] }
```

Shapes paint in declaration order. `t` is one of `rect`, `circle`, `line`, `path`,
`text`; an unknown one is a hard error rather than a silently missing feature.

Two rules that are not stylistic:

- **A pin coordinate must sit on or beyond the body outline.** Wires are routed to
  it, and a pin buried inside the art is a wire that disappears under a component.
- **`ghost: true`** marks a part that is specified but *not purchased* — it renders
  faded. [`../../BOM.csv`](../../BOM.csv) is what decides that, not this file.

Run `python3 tools/cirkit.py parts` for the whole vocabulary, local and imported
together.
