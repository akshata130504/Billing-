import { describe, expect, it } from 'vitest';
import { validatePersonName, validateSensibleName } from './validation';

// QA (new-bugs PDF, "Create Customer - Primary Contact"): mirrors backend validate_person_name.
describe('validatePersonName', () => {
  it.each(['José Ñúñez', 'محمد علي', "Mary-Jane O'Neil", 'Dr. A. Rao', '李小龙', 'Praveen V'])('accepts %s', (name) => {
    expect(validatePersonName(name, 'Contact name')).toBeNull();
  });

  it.each(['9876543', 'John123', 'x/y@z', 'Ravi #2', '<b>Jo</b>'])('rejects %s', (name) => {
    expect(validatePersonName(name, 'Contact name')).not.toBeNull();
  });

  it('requires a value', () => {
    expect(validatePersonName('  ', 'Contact name')).toBe('Contact name is required.');
  });

  it('leaves business names on the broader rule', () => {
    expect(validateSensibleName('Rooman Technologies 2.0 #1/A', 'Display name')).toBeNull();
  });
});
