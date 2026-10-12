#!/usr/bin/env bash
# La MI300X a finestre: nasce da uno snapshot quando serve e si distrugge quando non serve, perché anche
# spenta si paga (2,59 $ l'ora). AMD Developer Cloud è costruita su DigitalOcean: stessa API /v2, stesso token.
#
#   casa/mi300x/mi300x.sh conto              il token funziona? e il saldo
#   casa/mi300x/mi300x.sh stato              le MI300X accese con il nostro tag, con IP
#   casa/mi300x/mi300x.sh crea               dall'ultimo snapshot golden-*; se ce n'è già una, non ne crea un'altra
#   casa/mi300x/mi300x.sh distruggi          tutte quelle con il nostro tag, poi ricontrolla che non ne resti nessuna
#   casa/mi300x/mi300x.sh snapshot [id]      spegne la macchina e ne fa lo snapshot golden-AAAAMMGG-HHMM
#   casa/mi300x/mi300x.sh finestre <file>    accesa durante le finestre del file (finestre.json), distrutta fuori
#
# Variabili:
#   DIGITALOCEAN_ACCESS_TOKEN  il token personale del team AMD (obbligatorio)
#   DO_API                     predefinito https://api.digitalocean.com; se non accetta il token AMD,
#                              https://api.devcloud.amd.com (da provare il 12/10 con `conto`)
#   MI300X_TAG                 predefinito sportello-mi300x; `finestre` usa sportello-finestra, così non tocca mai
#                              una macchina accesa a mano per lavorare
#   MI300X_SSH                 l'impronta di una chiave SSH già aggiunta al team (per crea)
#   MI300X_AVVIO               un file cloud-init da passare alla nascita (facoltativo)
#   MI300X_SALUTE              un indirizzo da aspettare dopo la nascita, per esempio https://motore.example.org/salute
#   MI300X_DNS_DOMINIO, MI300X_DNS_NOME   se il dominio sta nel DNS di DigitalOcean: il record A da puntare all'IP
#   MI300X_ATTESA              secondi fra due controlli (predefinito 15)
#   MI300X_ANTICIPO            minuti di anticipo sull'inizio di una finestra (predefinito 45)
#   MI300X_RITENTA             quante volte si ritenta una lettura fallita (predefinito 3)
set -euo pipefail

API="${DO_API:-https://api.digitalocean.com}"
ATTESA="${MI300X_ATTESA:-15}"
TAGLIA="gpu-mi300x1-192gb" # 1× MI300X, 192 GB
REGIONE="atl1"             # l'unica con le MI300X

ferma() {
	echo "mi300x: $*" >&2
	exit 1
}

# Le letture si ritentano; le scritture no, perché una creazione ritentata potrebbe accendere due macchine.
leggi() { curl -fsS --retry "${MI300X_RITENTA:-3}" --retry-delay 5 -H "Authorization: Bearer $DIGITALOCEAN_ACCESS_TOKEN" "$@"; }
scrivi() { curl -fsS -H "Authorization: Bearer $DIGITALOCEAN_ACCESS_TOKEN" -H "Content-Type: application/json" "$@"; }

# Le macchine accese con il tag. Senza type=gpus l'elenco nasconde le GPU, e type non si combina con tag_name:
# si filtra qui. Se l'elenco fallisce, lo script si ferma prima di creare o distruggere qualcosa.
accese() {
	leggi "$API/v2/droplets?type=gpus&per_page=200" | jq -r --arg t "$TAG" '.droplets[] | select(any(.tags[]?; . == $t)) | .id'
}

stato_di() { leggi "$API/v2/droplets/$1" | jq -r .droplet.status; }
ip_di() { leggi "$API/v2/droplets/$1" | jq -r '[.droplet.networks.v4[]? | select(.type == "public") | .ip_address][0] // empty'; }

conto() {
	leggi "$API/v2/account" | jq -r '.account | "account \(.email // "?"): \(.status)"'
	leggi "$API/v2/customers/my/balance" 2>/dev/null |
		jq -r '"usati questo mese: \(.month_to_date_usage) $; saldo: \(.account_balance) $ (negativo = credito)"' || true
}

stato() {
	local ids id
	ids=$(accese)
	if [ -z "$ids" ]; then
		echo "spenta: nessuna MI300X con il tag $TAG"
		return 0
	fi
	for id in $ids; do
		leggi "$API/v2/droplets/$id" | jq -r '.droplet | "\(.id) \(.name) \(.status) IP \([.networks.v4[]? | select(.type == "public") | .ip_address][0] // "-") dal \(.created_at)"'
	done
}

punta_dns() { # $1 = IP; solo se il dominio sta nel DNS di DigitalOcean
	[ -n "${MI300X_DNS_DOMINIO:-}" ] && [ -n "${MI300X_DNS_NOME:-}" ] && [ -n "$1" ] || return 0
	local record attuale
	record=$(leggi "$API/v2/domains/$MI300X_DNS_DOMINIO/records?type=A&name=$MI300X_DNS_NOME.$MI300X_DNS_DOMINIO" | jq -r '.domain_records[0] | "\(.id) \(.data)"')
	attuale="${record#* }"
	if [ "$record" = "null null" ]; then
		scrivi -X POST "$API/v2/domains/$MI300X_DNS_DOMINIO/records" \
			-d "$(jq -n --arg n "$MI300X_DNS_NOME" --arg ip "$1" '{type: "A", name: $n, data: $ip, ttl: 60}')" >/dev/null
	elif [ "$attuale" != "$1" ]; then
		scrivi -X PUT "$API/v2/domains/$MI300X_DNS_DOMINIO/records/${record%% *}" -d "$(jq -n --arg ip "$1" '{data: $ip}')" >/dev/null
	else
		return 0
	fi
	echo "DNS: $MI300X_DNS_NOME.$MI300X_DNS_DOMINIO → $1"
}

crea() { # $1 = "aspetta" per aspettare che sia attiva (e il motore, con MI300X_SALUTE)
	local ids immagine corpo inizio id ip
	ids=$(accese)
	if [ -n "$ids" ]; then
		echo "già accesa, non ne creo un'altra: $ids"
		return 0
	fi
	[ -n "${MI300X_SSH:-}" ] || ferma "manca MI300X_SSH: l'impronta di una chiave SSH già aggiunta al team"
	immagine=$(leggi "$API/v2/snapshots?resource_type=droplet&per_page=200" |
		jq -r '[.snapshots[] | select(.name | startswith("golden-"))] | sort_by(.created_at) | last | .id // empty')
	[ -n "$immagine" ] || ferma "nessuno snapshot golden-*: prima si prepara una macchina e se ne fa lo snapshot (README)"
	corpo=$(jq -n --arg nome "sportello-$(date -u +%Y%m%d-%H%M)" --argjson immagine "$immagine" --arg tag "$TAG" \
		--arg ssh "$MI300X_SSH" --arg taglia "$TAGLIA" --arg regione "$REGIONE" \
		'{name: $nome, region: $regione, size: $taglia, image: $immagine, ssh_keys: [$ssh], tags: [$tag]}')
	if [ -n "${MI300X_AVVIO:-}" ]; then
		corpo=$(jq --rawfile avvio "$MI300X_AVVIO" '. + {user_data: $avvio}' <<<"$corpo")
	fi
	inizio=$(date +%s)
	id=$(scrivi -X POST "$API/v2/droplets" -d "$corpo" | jq -r '.droplet.id // empty')
	[ -n "$id" ] || ferma "la creazione non ha restituito un id"
	echo "creata $id dallo snapshot $immagine"
	[ "${1:-}" = aspetta ] || return 0
	for _ in $(seq 240); do # al massimo un'ora
		[ "$(stato_di "$id")" = active ] && break
		sleep "$ATTESA"
	done
	[ "$(stato_di "$id")" = active ] || ferma "dopo un'ora $id non è ancora attiva: se non serve va distrutta"
	ip=$(ip_di "$id")
	echo "attiva in $(($(date +%s) - inizio)) s, IP $ip"
	punta_dns "$ip"
	if [ -n "${MI300X_SALUTE:-}" ]; then
		for _ in $(seq 240); do
			curl -fsS -m 10 "$MI300X_SALUTE" >/dev/null 2>&1 && break
			sleep "$ATTESA"
		done
		curl -fsS -m 10 "$MI300X_SALUTE" >/dev/null 2>&1 || ferma "il motore non risponde su $MI300X_SALUTE"
		echo "motore pronto in $(($(date +%s) - inizio)) s"
	fi
}

distruggi() {
	local ids id
	ids=$(accese)
	for id in $ids; do
		scrivi -X DELETE "$API/v2/droplets/$id" >/dev/null
		echo "distrutta $id"
	done
	for _ in $(seq 20); do
		ids=$(accese)
		[ -z "$ids" ] && break
		sleep "$ATTESA"
	done
	[ -z "$ids" ] || ferma "ATTENZIONE: risultano ancora accese ($ids) e si pagano: vanno distrutte dal pannello"
	echo "nessuna MI300X accesa con il tag $TAG"
}

snapshot() {
	local id="${1:-}" azione s inizio
	[ -n "$id" ] || id=$(accese | head -n 1)
	[ -n "$id" ] || ferma "nessuna MI300X accesa da cui fare lo snapshot"
	scrivi -X POST "$API/v2/droplets/$id/actions" -d '{"type":"shutdown"}' >/dev/null
	for _ in $(seq 40); do
		[ "$(stato_di "$id")" = off ] && break
		sleep "$ATTESA"
	done
	if [ "$(stato_di "$id")" != off ]; then
		scrivi -X POST "$API/v2/droplets/$id/actions" -d '{"type":"power_off"}' >/dev/null
		for _ in $(seq 40); do
			[ "$(stato_di "$id")" = off ] && break
			sleep "$ATTESA"
		done
	fi
	[ "$(stato_di "$id")" = off ] || ferma "$id non si spegne: niente snapshot"
	inizio=$(date +%s)
	azione=$(scrivi -X POST "$API/v2/droplets/$id/actions" \
		-d "$(jq -n --arg n "golden-$(date -u +%Y%m%d-%H%M)" '{type: "snapshot", name: $n}')" | jq -r '.action.id // empty')
	[ -n "$azione" ] || ferma "lo snapshot non è partito"
	while s=$(leggi "$API/v2/actions/$azione" | jq -r .action.status) && [ "$s" = in-progress ]; do
		sleep "$ATTESA" # circa 1-3 minuti per GB usato
	done
	[ "$s" = completed ] || ferma "snapshot $azione: $s"
	echo "snapshot fatto in $(($(date +%s) - inizio)) s. La macchina $id è spenta ma si paga ancora: va distrutta (distruggi)."
}

finestre() { # $1 = finestre.json: [{"inizio": "2026-10-19T09:00:00+02:00", "fine": "2026-10-19T19:00:00+02:00"}, …]
	[ -f "${1:-}" ] || ferma "serve il file delle finestre"
	local adesso dentro
	adesso=$(date -u +%s)
	# L'ora con il fuso (2026-10-19T09:00:00+02:00) in secondi UTC: mktime di jq ignorerebbe il fuso.
	dentro=$(jq --argjson adesso "$adesso" --argjson anticipo "$((${MI300X_ANTICIPO:-45} * 60))" '
		def secondi: capture("^(?<t>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\\.[0-9]+)?(?<z>Z|[+-][0-9]{2}:?[0-9]{2})$") as $c
			| ($c.t + "Z" | fromdateiso8601)
			- (if $c.z == "Z" then 0 else ($c.z[1:3] | tonumber) * 3600 + ($c.z[-2:] | tonumber) * 60
				| if $c.z[0:1] == "-" then -. else . end end);
		[.[] | select($adesso >= (.inizio | secondi) - $anticipo and $adesso < (.fine | secondi))] | length > 0' "$1")
	if [ "$dentro" = true ]; then
		echo "dentro una finestra: la MI300X deve essere accesa"
		crea
		local id
		for id in $(accese); do punta_dns "$(ip_di "$id")"; done
	else
		echo "fuori dalle finestre: la MI300X deve essere spenta"
		distruggi
	fi
}

case "${1:-}" in
conto | stato | crea | distruggi | snapshot | finestre) ;;
*)
	echo "uso: $0 conto | stato | crea [aspetta] | distruggi | snapshot [id] | finestre <finestre.json>" >&2
	exit 2
	;;
esac
[ -n "${DIGITALOCEAN_ACCESS_TOKEN:-}" ] || ferma "manca DIGITALOCEAN_ACCESS_TOKEN"
if [ "$1" = finestre ]; then
	TAG="${MI300X_TAG:-sportello-finestra}"
else
	TAG="${MI300X_TAG:-sportello-mi300x}"
fi
comando="$1"
shift
"$comando" "$@"
