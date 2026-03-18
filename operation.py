from typing import Optional


class Operation:
    def __init__(
        self,
        date: str,
        exit: Optional[str],
        close: Optional[str],
        typology: str,
        raw_x: Optional[str] = None,
        raw_y: Optional[str] = None,
        loc: str = "",
        add: str = "",
        opn: str = "",
        nom: str = "",
        boss: str = "",
    ):
        self.date = date
        self.exit = exit
        self.close = close
        self.typology = typology
        self.loc = loc
        self.add = add
        self.opn = opn
        self.nom = nom
        self.boss = boss
        self.x = self._parse_coord(raw_x)
        self.y = self._parse_coord(raw_y)

    @staticmethod
    def _parse_coord(raw: Optional[str]) -> str:
        """Extract numeric coordinate from strings like 'X: 8,20165495'."""
        if raw is None:
            return "---"
        value = raw.split(":")[-1].strip().replace(",", ".")
        try:
            float(value)
            return value
        except ValueError:
            return "---"

    def __repr__(self) -> str:
        return (
            f"Operation(opn={self.opn!r}, date={self.date!r}, exit={self.exit!r}, "
            f"close={self.close!r}, typology={self.typology!r}, "
            f"x={self.x!r}, y={self.y!r}, loc={self.loc!r})"
        )