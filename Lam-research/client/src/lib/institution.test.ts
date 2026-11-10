import { describe, expect, it } from 'vitest';
import { formatInstitutionDisplay } from './institution';

describe('formatInstitutionDisplay', () => {
  it('keeps the real institution when present', () => {
    expect(formatInstitutionDisplay('Stanford University', 'California', 'US')).toBe('Stanford University');
  });

  it('falls back to location when institution is missing', () => {
    expect(formatInstitutionDisplay('', 'California', 'US')).toBe('California, United States');
    expect(formatInstitutionDisplay(null, 'Baden-Württemberg', 'DE')).toBe('Baden-Württemberg, Germany');
  });

  it('avoids the misleading unknown message when the institution is blank', () => {
    expect(formatInstitutionDisplay('Unknown institution', null, 'US')).toBe('United States');
    expect(formatInstitutionDisplay('unknown', 'California', null)).toBe('California');
  });
});
