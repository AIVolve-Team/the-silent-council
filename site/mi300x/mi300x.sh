#!/usr/bin/env bash
# The MI300X in windows: it is born from a snapshot when needed and destroyed when not, because even
# powered off it is billed ($2.59 an hour). AMD Developer Cloud is built on DigitalOcean: same /v2 API, same token.
#
#   site/mi300x/mi300x.sh account           does the token work? and the balance
#   site/mi300x/mi300x.sh status            the MI300X machines running with our tag, with their IP
#   site/mi300x/mi300x.sh create [wait]     from the latest golden-* snapshot; if one is already running, no second one
#   site/mi300x/mi300x.sh destroy           every machine with our tag, then checks again that none is left
#   site/mi300x/mi300x.sh snapshot [id]     powers the machine off and takes the snapshot golden-YYYYMMDD-HHMM
#   site/mi300x/mi300x.sh windows <file>    running during the windows of the file (windows.json), destroyed outside
#
# Variables:
#   DIGITALOCEAN_ACCESS_TOKEN  the personal token of the AMD team (required)
#   DO_API                     default https://api.digitalocean.com; if it does not accept the AMD token,
#                              https://api.devcloud.amd.com (to be tried on 12/10 with `account`)
#   MI300X_TAG                 default council-mi300x; `windows` uses council-window, so it never touches
#                              a machine started by hand to work on
#   MI300X_SSH                 the fingerprint of an SSH key already added to the team (for create)
#   MI300X_CLOUD_INIT          a cloud-init file to pass at birth (optional)
#   MI300X_HEALTH              an address to wait for after birth, for example https://engine.example.org/health
#   MI300X_DNS_DOMAIN, MI300X_DNS_NAME   if the domain is in DigitalOcean's DNS: the A record to point at the IP
#   MI300X_POLL                seconds between two checks (default 15)
#   MI300X_LEAD                minutes ahead of the start of a window (default 45)
#   MI300X_RETRIES             how many times a failed read is retried (default 3)
#
# Machines started by the old code carry the tags of the Help Desk (sportello-mi300x, sportello-finestra): every
# command also sees the legacy tag that matches its tag (LEGACY_TAGS), so `status` shows them, `destroy` destroys
# them and `create` does not start a second machine next to one of them. New machines only get the new tag.
set -euo pipefail

API="${DO_API:-https://api.digitalocean.com}"
POLL="${MI300X_POLL:-15}"
SIZE="gpu-mi300x1-192gb" # 1× MI300X, 192 GB
REGION="atl1"            # the only one with MI300X
# new tag=legacy tag
LEGACY_TAGS="council-mi300x=sportello-mi300x council-window=sportello-finestra"

fail() {
	echo "mi300x: $*" >&2
	exit 1
}

# Reads are retried; writes are not, because a retried creation could start two machines.
read_api() { curl -fsS --retry "${MI300X_RETRIES:-3}" --retry-delay 5 -H "Authorization: Bearer $DIGITALOCEAN_ACCESS_TOKEN" "$@"; }
write_api() { curl -fsS -H "Authorization: Bearer $DIGITALOCEAN_ACCESS_TOKEN" -H "Content-Type: application/json" "$@"; }

# The tag plus its legacy tag, if it has one.
tags_for() {
	local pair tags="$1"
	for pair in $LEGACY_TAGS; do
		[ "${pair%%=*}" = "$1" ] && tags="$tags ${pair#*=}"
	done
	echo "$tags"
}

# The machines running with one of the tags. Without type=gpus the list hides the GPUs, and type does not combine
# with tag_name: the filtering happens here. If the list fails, the script stops before creating or destroying anything.
running() {
	read_api "$API/v2/droplets?type=gpus&per_page=200" |
		jq -r --arg t "$TAGS" '($t | split(" ")) as $tags | .droplets[] | select(any(.tags[]?; . as $x | any($tags[]; . == $x))) | .id'
}

status_of() { read_api "$API/v2/droplets/$1" | jq -r .droplet.status; }
ip_of() { read_api "$API/v2/droplets/$1" | jq -r '[.droplet.networks.v4[]? | select(.type == "public") | .ip_address][0] // empty'; }

account() {
	read_api "$API/v2/account" | jq -r '.account | "account \(.email // "?"): \(.status)"'
	read_api "$API/v2/customers/my/balance" 2>/dev/null |
		jq -r '"used this month: $\(.month_to_date_usage); balance: $\(.account_balance) (negative = credit)"' || true
}

status() {
	local ids id
	ids=$(running)
	if [ -z "$ids" ]; then
		echo "off: no MI300X with the tags $TAGS"
		return 0
	fi
	for id in $ids; do
		read_api "$API/v2/droplets/$id" | jq -r '.droplet | "\(.id) \(.name) \(.status) IP \([.networks.v4[]? | select(.type == "public") | .ip_address][0] // "-") since \(.created_at)"'
	done
}

point_dns() { # $1 = IP; only if the domain is in DigitalOcean's DNS
	[ -n "${MI300X_DNS_DOMAIN:-}" ] && [ -n "${MI300X_DNS_NAME:-}" ] && [ -n "$1" ] || return 0
	local record current
	record=$(read_api "$API/v2/domains/$MI300X_DNS_DOMAIN/records?type=A&name=$MI300X_DNS_NAME.$MI300X_DNS_DOMAIN" | jq -r '.domain_records[0] | "\(.id) \(.data)"')
	current="${record#* }"
	if [ "$record" = "null null" ]; then
		write_api -X POST "$API/v2/domains/$MI300X_DNS_DOMAIN/records" \
			-d "$(jq -n --arg n "$MI300X_DNS_NAME" --arg ip "$1" '{type: "A", name: $n, data: $ip, ttl: 60}')" >/dev/null
	elif [ "$current" != "$1" ]; then
		write_api -X PUT "$API/v2/domains/$MI300X_DNS_DOMAIN/records/${record%% *}" -d "$(jq -n --arg ip "$1" '{data: $ip}')" >/dev/null
	else
		return 0
	fi
	echo "DNS: $MI300X_DNS_NAME.$MI300X_DNS_DOMAIN → $1"
}

create() { # $1 = "wait" to wait until it is active (and the engine, with MI300X_HEALTH)
	local ids image body start id ip
	ids=$(running)
	if [ -n "$ids" ]; then
		echo "already running, not creating another one: $ids"
		return 0
	fi
	[ -n "${MI300X_SSH:-}" ] || fail "MI300X_SSH is missing: the fingerprint of an SSH key already added to the team"
	image=$(read_api "$API/v2/snapshots?resource_type=droplet&per_page=200" |
		jq -r '[.snapshots[] | select(.name | startswith("golden-"))] | sort_by(.created_at) | last | .id // empty')
	[ -n "$image" ] || fail "no golden-* snapshot: first prepare a machine and take its snapshot (README)"
	body=$(jq -n --arg name "council-$(date -u +%Y%m%d-%H%M)" --argjson image "$image" --arg tag "$TAG" \
		--arg ssh "$MI300X_SSH" --arg size "$SIZE" --arg region "$REGION" \
		'{name: $name, region: $region, size: $size, image: $image, ssh_keys: [$ssh], tags: [$tag]}')
	if [ -n "${MI300X_CLOUD_INIT:-}" ]; then
		body=$(jq --rawfile init "$MI300X_CLOUD_INIT" '. + {user_data: $init}' <<<"$body")
	fi
	start=$(date +%s)
	id=$(write_api -X POST "$API/v2/droplets" -d "$body" | jq -r '.droplet.id // empty')
	[ -n "$id" ] || fail "the creation returned no id"
	echo "created $id from the snapshot $image"
	[ "${1:-}" = wait ] || return 0
	for _ in $(seq 240); do # one hour at most
		[ "$(status_of "$id")" = active ] && break
		sleep "$POLL"
	done
	[ "$(status_of "$id")" = active ] || fail "after one hour $id is still not active: if it is not needed it must be destroyed"
	ip=$(ip_of "$id")
	echo "active in $(($(date +%s) - start)) s, IP $ip"
	point_dns "$ip"
	if [ -n "${MI300X_HEALTH:-}" ]; then
		for _ in $(seq 240); do
			curl -fsS -m 10 "$MI300X_HEALTH" >/dev/null 2>&1 && break
			sleep "$POLL"
		done
		curl -fsS -m 10 "$MI300X_HEALTH" >/dev/null 2>&1 || fail "the engine does not answer on $MI300X_HEALTH"
		echo "engine ready in $(($(date +%s) - start)) s"
	fi
}

destroy() {
	local ids id
	ids=$(running)
	for id in $ids; do
		write_api -X DELETE "$API/v2/droplets/$id" >/dev/null
		echo "destroyed $id"
	done
	for _ in $(seq 20); do
		ids=$(running)
		[ -z "$ids" ] && break
		sleep "$POLL"
	done
	[ -z "$ids" ] || fail "WARNING: still running ($ids) and billed: they must be destroyed from the control panel"
	echo "no MI300X running with the tags $TAGS"
}

snapshot() {
	local id="${1:-}" action s start
	[ -n "$id" ] || id=$(running | head -n 1)
	[ -n "$id" ] || fail "no MI300X running to take the snapshot from"
	write_api -X POST "$API/v2/droplets/$id/actions" -d '{"type":"shutdown"}' >/dev/null
	for _ in $(seq 40); do
		[ "$(status_of "$id")" = off ] && break
		sleep "$POLL"
	done
	if [ "$(status_of "$id")" != off ]; then
		write_api -X POST "$API/v2/droplets/$id/actions" -d '{"type":"power_off"}' >/dev/null
		for _ in $(seq 40); do
			[ "$(status_of "$id")" = off ] && break
			sleep "$POLL"
		done
	fi
	[ "$(status_of "$id")" = off ] || fail "$id does not power off: no snapshot"
	start=$(date +%s)
	action=$(write_api -X POST "$API/v2/droplets/$id/actions" \
		-d "$(jq -n --arg n "golden-$(date -u +%Y%m%d-%H%M)" '{type: "snapshot", name: $n}')" | jq -r '.action.id // empty')
	[ -n "$action" ] || fail "the snapshot did not start"
	while s=$(read_api "$API/v2/actions/$action" | jq -r .action.status) && [ "$s" = in-progress ]; do
		sleep "$POLL" # about 1-3 minutes per GB used
	done
	[ "$s" = completed ] || fail "snapshot $action: $s"
	echo "snapshot taken in $(($(date +%s) - start)) s. The machine $id is off but still billed: it must be destroyed (destroy)."
}

windows() { # $1 = windows.json: [{"start": "2026-10-19T09:00:00+02:00", "end": "2026-10-19T19:00:00+02:00"}, …]
	[ -f "${1:-}" ] || fail "the windows file is needed"
	local now inside
	now=$(date -u +%s)
	# The time with its offset (2026-10-19T09:00:00+02:00) in UTC seconds: jq's mktime would ignore the offset.
	inside=$(jq --argjson now "$now" --argjson lead "$((${MI300X_LEAD:-45} * 60))" '
		def seconds: capture("^(?<t>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(\\.[0-9]+)?(?<z>Z|[+-][0-9]{2}:?[0-9]{2})$") as $c
			| ($c.t + "Z" | fromdateiso8601)
			- (if $c.z == "Z" then 0 else ($c.z[1:3] | tonumber) * 3600 + ($c.z[-2:] | tonumber) * 60
				| if $c.z[0:1] == "-" then -. else . end end);
		[.[] | select($now >= (.start | seconds) - $lead and $now < (.end | seconds))] | length > 0' "$1")
	if [ "$inside" = true ]; then
		echo "inside a window: the MI300X must be running"
		create
		local id
		for id in $(running); do point_dns "$(ip_of "$id")"; done
	else
		echo "outside the windows: the MI300X must be off"
		destroy
	fi
}

case "${1:-}" in
account | status | create | destroy | snapshot | windows) ;;
*)
	echo "usage: $0 account | status | create [wait] | destroy | snapshot [id] | windows <windows.json>" >&2
	exit 2
	;;
esac
[ -n "${DIGITALOCEAN_ACCESS_TOKEN:-}" ] || fail "DIGITALOCEAN_ACCESS_TOKEN is missing"
if [ "$1" = windows ]; then
	TAG="${MI300X_TAG:-council-window}"
else
	TAG="${MI300X_TAG:-council-mi300x}"
fi
TAGS=$(tags_for "$TAG")
cmd="$1"
shift
"$cmd" "$@"
