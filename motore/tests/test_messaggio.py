"""Test senza modello: impronta, file, catena e firma."""

import torch

from motore import ControlloCatena, ControlloImpronta, ControlloSigillo, MessaggioLatente
from motore.sigillo import carica_private, carica_pubbliche, crea_chiavi, firma

from .conftest import messaggio_finto


def test_un_byte_cambiato_si_vede():
    messaggio = messaggio_finto()
    assert ControlloImpronta()(messaggio, []).passa
    messaggio.kv_lettura[1][0].view(-1)[5] += 1e-6
    esito = ControlloImpronta()(messaggio, [])
    assert not esito.passa and "lettura" in esito.motivo


def test_etichetta_cambiata_si_vede():
    messaggio = messaggio_finto()
    messaggio.etichetta["mittente"] = "finanza"
    assert not ControlloImpronta()(messaggio, []).passa


def test_salvato_e_ricaricato_senza_perdite(tmp_path):
    messaggio = messaggio_finto()
    messaggio.salva(tmp_path / "m.safetensors", completo=True)
    ricaricato = MessaggioLatente.carica(tmp_path / "m.safetensors")
    assert ricaricato.etichetta == messaggio.etichetta
    for (k1, v1), (k2, v2) in zip(
        messaggio.kv_lettura + messaggio.kv_pensieri, ricaricato.kv_lettura + ricaricato.kv_pensieri
    ):
        assert torch.equal(k1, k2) and torch.equal(v1, v2)
    assert ControlloImpronta()(ricaricato, []).passa


def test_salvataggio_ridotto_tiene_etichetta_e_stati(tmp_path):
    messaggio = messaggio_finto()
    messaggio.salva(tmp_path / "m.safetensors")
    ricaricato = MessaggioLatente.carica(tmp_path / "m.safetensors")
    assert ricaricato.kv_lettura == [] and torch.equal(ricaricato.stati, messaggio.stati)
    assert ricaricato.etichetta["hash_blocchi"]["stati"] == ricaricato.hash_blocchi()["stati"]


def test_la_copia_e_indipendente():
    messaggio = messaggio_finto()
    copia = messaggio.copia()
    copia.kv_lettura[0][0].zero_()
    assert ControlloImpronta()(messaggio, []).passa


def test_catena():
    controllo = ControlloCatena("finto", "0")
    primo = messaggio_finto()
    assert controllo(primo, []).passa
    secondo = messaggio_finto(numero=2, inizio=primo.lunghezza, precedente=primo.impronta, seme=1)
    assert controllo(secondo, [primo]).passa
    rispedito = messaggio_finto(numero=2, inizio=primo.lunghezza, precedente="altro", seme=1)
    assert "precedente" in controllo(rispedito, [primo]).motivo
    spostato = messaggio_finto(numero=2, inizio=primo.lunghezza + 1, precedente=primo.impronta, seme=1)
    assert "non si sposta" in controllo(spostato, [primo]).motivo
    fuori_ordine = messaggio_finto(numero=3, inizio=primo.lunghezza, precedente=primo.impronta, seme=1)
    assert "numero" in controllo(fuori_ordine, [primo]).motivo
    altra_sessione = messaggio_finto(numero=2, sessione="t", inizio=primo.lunghezza, precedente=primo.impronta)
    assert "sessione" in controllo(altra_sessione, [primo]).motivo
    assert "modello" in ControlloCatena("altro", "0")(primo, []).motivo


def test_firma(tmp_path):
    crea_chiavi(tmp_path / "private", tmp_path / "pubbliche", ["legale", "finanza"])
    private = carica_private(tmp_path / "private", ["legale", "finanza"])
    controllo = ControlloSigillo(carica_pubbliche(tmp_path / "pubbliche"))
    assert (tmp_path / "private" / "legale.pem").stat().st_mode & 0o777 == 0o600

    messaggio = messaggio_finto()
    assert controllo(messaggio, []).motivo == "messaggio non firmato"
    firma(messaggio, private["legale"])
    assert controllo(messaggio, []).passa

    # Chi manomette può ricalcolare hash e impronta, ma non la firma.
    messaggio.kv_lettura[0][0].view(-1)[0] += 1
    messaggio.etichetta["hash_blocchi"] = messaggio.hash_blocchi()
    assert ControlloImpronta()(messaggio.copia().chiudi(), []).passa
    assert "firma non valida" in controllo(messaggio, []).motivo

    finto = messaggio_finto()
    firma(finto, private["finanza"])
    assert "firma non valida per legale" in controllo(finto, []).motivo


def test_token_ammessi_da_lista_e_da_maschera_di_bit():
    from lmformatenforcer.tokenlist import TokenList

    from motore.motore import token_ammessi

    for maschera in (False, True):
        ammessi = TokenList(use_bitmask=maschera, vocab_size=70)
        ammessi.extend([0, 31, 32, 69])
        assert token_ammessi(ammessi) == [0, 31, 32, 69]


def test_verifica_archivio_anche_senza_kv(tmp_path):
    from motore.verifica import verifica_archivio

    crea_chiavi(tmp_path / "private", tmp_path / "pubbliche", ["legale"])
    chiave = carica_private(tmp_path / "private", ["legale"])["legale"]
    primo = messaggio_finto()
    firma(primo, chiave)
    secondo = messaggio_finto(numero=2, inizio=primo.lunghezza, precedente=primo.impronta, seme=1)
    firma(secondo, chiave)
    primo.salva(tmp_path / "1.safetensors")
    secondo.salva(tmp_path / "2.safetensors", completo=True)
    file = [tmp_path / "1.safetensors", tmp_path / "2.safetensors"]
    assert all(esito.passa for _, esito in verifica_archivio(file, tmp_path / "pubbliche"))

    # Senza il primo messaggio la catena non torna.
    assert not verifica_archivio(file[1:], tmp_path / "pubbliche")[0][1].passa

    # Un messaggio rifirmato con un'altra chiave non passa.
    crea_chiavi(tmp_path / "altre", tmp_path / "altre-pubbliche", ["legale"])
    firma(secondo, carica_private(tmp_path / "altre", ["legale"])["legale"])
    secondo.salva(tmp_path / "2.safetensors", completo=True)
    assert "firma non valida" in verifica_archivio(file, tmp_path / "pubbliche")[1][1].motivo


def test_maschera_ammessi_da_lista_e_da_bit():
    from lmformatenforcer.tokenlist import TokenList

    from motore.motore import maschera_ammessi

    for bit in (False, True):
        ammessi = TokenList(use_bitmask=bit, vocab_size=70)
        ammessi.extend([0, 31, 32, 69])
        assert maschera_ammessi(ammessi).nonzero().flatten().tolist() == [0, 31, 32, 69]
