from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal, Optional

CollectionMode = Literal["sample", "live", "import"]
AnalysisMode = Literal["local", "gemini"]
Consonancia = Literal["CONSONANCIA", "DISSONANCIA", "NAO_APLICAVEL"]
ValidadeAnalise = Literal["VALIDA", "INCOMPLETA", "INVALIDA"]
RecursalAction = Literal["SOBRESTAR", "NEGAR_SEGUIMENTO", "DETERMINAR_ADEQUACAO", "SEM_ACAO"]


@dataclass(slots=True)
class TnuTheme:
    temaNumero: str
    situacaoTema: str
    ramoDireito: str
    questaoSubmetidaJulgamento: str
    teseFirmada: str
    numeroProcesso: str
    dataDecisaoAfetacao: str
    relator: str
    dataJulgamento: str
    dataPublicacaoAcordao: str
    transitoJulgado: str
    pdfPath: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Trf2Decision:
    decisionId: str
    classe: str
    tipoJulgamento: str
    assuntos: str
    competencia: str
    relatorOriginario: str
    dataAutuacao: str
    dataJulgamento: str
    numeroProcesso: str
    inteiroTeorPath: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AnalysisOutput:
    decisionId: str
    temaTnu: str
    consonancia: Consonancia
    validade: ValidadeAnalise
    justificativa: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class DocumentDecision:
    decisionId: str
    temaTnu: str
    action: RecursalAction

    def to_dict(self) -> dict:
        return asdict(self)
