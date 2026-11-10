const UNKNOWN_VALUES = new Set(['unknown', 'unknown institution', 'n/a', 'null']);

function countryNameFromCode(code?: string | null): string | undefined {
  const normalized = code?.trim();
  if (!normalized || normalized.length !== 2 || !/^[A-Za-z]{2}$/.test(normalized)) {
    return undefined;
  }

  try {
    const displayNames = new Intl.DisplayNames(['en'], { type: 'region' });
    return displayNames.of(normalized.toUpperCase()) ?? undefined;
  } catch {
    return undefined;
  }
}

export function normalizeLocationLabel(region?: string | null, countryCode?: string | null): string {
  const regionText = region?.trim();
  const countryLabel = countryNameFromCode(countryCode) ?? countryCode?.trim();

  if (!regionText) {
    return countryLabel || 'Unknown';
  }

  if (countryLabel && regionText.toLowerCase() === countryLabel.toLowerCase()) {
    return countryLabel;
  }

  return countryLabel ? `${regionText}, ${countryLabel}` : regionText;
}

export function formatInstitutionDisplay(
  institution?: string | null,
  region?: string | null,
  countryCode?: string | null,
): string {
  const raw = institution?.trim();
  if (raw && !UNKNOWN_VALUES.has(raw.toLowerCase())) {
    return raw;
  }

  const locationLabel = normalizeLocationLabel(region, countryCode);
  if (locationLabel && !UNKNOWN_VALUES.has(locationLabel.toLowerCase())) {
    return locationLabel;
  }

  return 'Institution unavailable';
}

export function formatResearcherInstitutionLabel(
  institution?: string | null,
  region?: string | null,
  country?: string | null,
): string {
  return formatInstitutionDisplay(institution, region, country);
}
