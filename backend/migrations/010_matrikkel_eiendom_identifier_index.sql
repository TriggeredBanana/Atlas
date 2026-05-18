-- Migration 010: helper index for MatrikkelenEiendomskartTeig property identifier searches.
-- Run outside a transaction because CREATE INDEX CONCURRENTLY cannot run inside one.

CREATE INDEX CONCURRENTLY IF NOT EXISTS matrikkelenhet_property_identifier_idx
ON matrikkel_eiendomskartteig.matrikkelenhet (
    kommunenummer,
    gardsnummer,
    bruksnummer,
    festenummer,
    seksjonsnummer
);
