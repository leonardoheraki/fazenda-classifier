"""A list of measured crowns, independent of Qt and numerical algorithms."""
from copy import deepcopy


class TreeBatch:
    def __init__(self):
        self._records = []
        self.finalized = False
        self.dirty = False

    def __len__(self):
        return len(self._records)

    @property
    def records(self):
        return tuple(deepcopy(record) for record in self._records)

    def add(self, record, tree_id, ua=""):
        # Validate before changing the list. A pending worker cannot be saved.
        record.as_csv_row()
        tree_id, ua = str(tree_id).strip(), str(ua).strip()
        if not tree_id:
            raise ValueError("Informe o identificador da árvore antes de adicioná-la à lista.")
        if any((r.ua, r.arvore_id) == (ua, tree_id) for r in self._records):
            raise ValueError(f"A árvore {tree_id} já está na lista dessa parcela. Confira o identificador.")
        snapshot = deepcopy(record)
        snapshot.arvore_id, snapshot.ua = tree_id, ua
        self._records.append(snapshot)
        self.finalized = False
        self.dirty = True
        return ua, tree_id

    def finalize(self):
        if not self._records:
            raise ValueError("Adicione pelo menos uma árvore à lista antes de finalizar.")
        self.finalized = True

    def resume(self):
        self.finalized = False

    def remove(self, index):
        record = self._records.pop(index)
        self.dirty = bool(self._records)
        if not self._records:
            self.finalized = False
        return record

    def mark_exported(self):
        self.dirty = False

    def clear(self):
        self._records.clear()
        self.finalized = False
        self.dirty = False
