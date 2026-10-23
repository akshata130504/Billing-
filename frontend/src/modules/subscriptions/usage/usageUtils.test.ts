import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  AGGREGATION_LABELS,
  BATCH_CSV_COLUMNS,
  datetimeLocalToIso,
  formatQuantity,
  newIdempotencyKey,
  normaliseApiTimestamp,
  parseBatchInput,
  toDatetimeLocalValue,
} from './usageUtils';

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AGGREGATION_LABELS', () => {
  it('covers every aggregation the meters API supports', () => {
    expect(Object.keys(AGGREGATION_LABELS).sort()).toEqual(['count', 'last', 'max', 'sum']);
    expect(AGGREGATION_LABELS.sum.label).toBe('Sum');
    for (const cfg of Object.values(AGGREGATION_LABELS)) {
      expect(cfg.hint.length).toBeGreaterThan(10);
    }
  });
});

describe('newIdempotencyKey', () => {
  it('returns a v4 UUID', () => {
    expect(newIdempotencyKey()).toMatch(UUID_V4);
  });

  it('returns a distinct key on every call', () => {
    const keys = new Set(Array.from({ length: 50 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(50);
  });

  it('falls back to a Math.random v4 key when crypto.randomUUID is missing', () => {
    vi.stubGlobal('crypto', {});
    const key = newIdempotencyKey();
    expect(key).toMatch(UUID_V4);
    expect(key).not.toBe(newIdempotencyKey());
  });

  it('stays within the backend 128-character limit', () => {
    expect(newIdempotencyKey().length).toBeLessThanOrEqual(128);
  });
});

describe('toDatetimeLocalValue / datetimeLocalToIso', () => {
  it('renders a datetime-local value with zero-padded local fields', () => {
    expect(toDatetimeLocalValue(new Date(2026, 8, 7, 9, 5))).toBe('2026-09-07T09:05');
    expect(toDatetimeLocalValue(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31T23:59');
  });

  it('round-trips through datetimeLocalToIso at minute precision', () => {
    const d = new Date(2026, 8, 7, 9, 5, 0, 0);
    const iso = datetimeLocalToIso(toDatetimeLocalValue(d));
    expect(iso).toBe(d.toISOString());
  });

  it('interprets the datetime-local value as local time, not UTC', () => {
    const iso = datetimeLocalToIso('2026-09-07T09:05');
    expect(iso).toBe(new Date(2026, 8, 7, 9, 5).toISOString());
  });

  it('returns null for blank or invalid values', () => {
    expect(datetimeLocalToIso('')).toBeNull();
    expect(datetimeLocalToIso('not-a-date')).toBeNull();
    expect(datetimeLocalToIso('2026-13-45T99:99')).toBeNull();
  });
});

describe('formatQuantity', () => {
  it('strips the trailing zeros the API sends on decimal quantities', () => {
    expect(formatQuantity('125.5000')).toBe('125.5');
    expect(formatQuantity('10.0000')).toBe('10');
    expect(formatQuantity('0.0001')).toBe('0.0001');
  });

  it('groups large quantities with en-IN separators', () => {
    expect(formatQuantity('1234567')).toBe('12,34,567');
  });

  it('keeps zero as a real value rather than an em dash', () => {
    expect(formatQuantity(0)).toBe('0');
    expect(formatQuantity('0.0000')).toBe('0');
  });

  it('returns an em dash for missing values', () => {
    expect(formatQuantity(null)).toBe('—');
    expect(formatQuantity(undefined)).toBe('—');
    expect(formatQuantity('')).toBe('—');
  });

  it('echoes back non-numeric input rather than showing NaN', () => {
    expect(formatQuantity('n/a')).toBe('n/a');
  });
});

describe('normaliseApiTimestamp', () => {
  it('appends Z to naive UTC datetimes returned by the meters API', () => {
    expect(normaliseApiTimestamp('2026-09-08T17:21:24.387285')).toBe('2026-09-08T17:21:24.387285Z');
    expect(normaliseApiTimestamp('2026-09-08T17:21:24')).toBe('2026-09-08T17:21:24Z');
    expect(normaliseApiTimestamp('2026-09-08T17:21')).toBe('2026-09-08T17:21Z');
  });

  it('leaves already-zoned timestamps untouched', () => {
    expect(normaliseApiTimestamp('2026-09-08T17:21:24Z')).toBe('2026-09-08T17:21:24Z');
    expect(normaliseApiTimestamp('2026-09-08T17:21:24+05:30')).toBe('2026-09-08T17:21:24+05:30');
  });

  it('leaves date-only and unknown formats untouched', () => {
    expect(normaliseApiTimestamp('2026-09-08')).toBe('2026-09-08');
  });

  it('returns null for missing values', () => {
    expect(normaliseApiTimestamp(null)).toBeNull();
    expect(normaliseApiTimestamp(undefined)).toBeNull();
    expect(normaliseApiTimestamp('')).toBeNull();
  });

  it('makes a naive timestamp parse as UTC (the whole point of the helper)', () => {
    const naive = '2026-09-08T17:21:24';
    expect(new Date(normaliseApiTimestamp(naive)!).toISOString()).toBe('2026-09-08T17:21:24.000Z');
  });
});

describe('parseBatchInput — empty input', () => {
  it('reports the empty format with no errors', () => {
    expect(parseBatchInput('')).toEqual({ events: [], errors: [], warnings: [], format: 'empty' });
    expect(parseBatchInput('   \n  ')).toEqual({ events: [], errors: [], warnings: [], format: 'empty' });
  });
});

describe('parseBatchInput — JSON', () => {
  it('parses an array of events and fills in the optional fields', () => {
    const res = parseBatchInput(
      JSON.stringify([{ meter_code: 'api_calls', customer_id: 'cus_1', quantity: 12.5 }])
    );
    expect(res.format).toBe('json');
    expect(res.errors).toEqual([]);
    expect(res.events).toHaveLength(1);
    expect(res.events[0]).toMatchObject({
      meter_code: 'api_calls',
      customer_id: 'cus_1',
      quantity: '12.5',
      subscription_id: null,
      timestamp: null,
      properties: null,
    });
    expect(res.events[0].idempotency_key).toMatch(UUID_V4);
  });

  it('accepts the { events: [...] } envelope', () => {
    const res = parseBatchInput(
      JSON.stringify({ events: [{ meter_code: 'gb', customer_id: 'c1', quantity: '1' }] })
    );
    expect(res.errors).toEqual([]);
    expect(res.events).toHaveLength(1);
    expect(res.events[0].meter_code).toBe('gb');
  });

  it('accepts "meter" as an alias for meter_code', () => {
    const res = parseBatchInput(JSON.stringify([{ meter: 'gb', customer_id: 'c1', quantity: '1' }]));
    expect(res.errors).toEqual([]);
    expect(res.events[0].meter_code).toBe('gb');
  });

  it('preserves a supplied idempotency key (no double-billing on retry)', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'gb', customer_id: 'c1', quantity: '1', idempotency_key: 'my-key-001' },
      ])
    );
    expect(res.events[0].idempotency_key).toBe('my-key-001');
  });

  it('rejects an idempotency key over 128 characters', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'gb', customer_id: 'c1', quantity: '1', idempotency_key: 'k'.repeat(129) },
      ])
    );
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/idempotency_key exceeds 128 characters/);
  });

  it('reports invalid JSON without throwing', () => {
    const res = parseBatchInput('[{"meter_code": ');
    expect(res.format).toBe('json');
    expect(res.events).toEqual([]);
    expect(res.errors).toHaveLength(1);
    expect(res.errors[0]).toMatch(/^Invalid JSON: /);
  });

  it('rejects a JSON object that is not an events envelope', () => {
    const res = parseBatchInput('{"foo": 1}');
    expect(res.events).toEqual([]);
    expect(res.errors).toEqual([
      'JSON must be an array of events or an object with an "events" array.',
    ]);
  });

  it('rejects non-object entries inside the array', () => {
    const res = parseBatchInput('[1, "x", null, []]');
    expect(res.events).toEqual([]);
    expect(res.errors).toEqual([
      'Event 1: must be an object',
      'Event 2: must be an object',
      'Event 3: must be an object',
      'Event 4: must be an object',
    ]);
  });

  it('parses a properties object and a properties JSON string', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'm', customer_id: 'c', quantity: '1', properties: { region: 'in' } },
        { meter_code: 'm', customer_id: 'c', quantity: '1', properties: '{"region":"us"}' },
      ])
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0].properties).toEqual({ region: 'in' });
    expect(res.events[1].properties).toEqual({ region: 'us' });
  });

  it('rejects properties that are not JSON objects', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'm', customer_id: 'c', quantity: '1', properties: '[1,2]' },
        { meter_code: 'm', customer_id: 'c', quantity: '1', properties: 'not json' },
        { meter_code: 'm', customer_id: 'c', quantity: '1', properties: 42 },
      ])
    );
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/properties must be a JSON object/);
    expect(res.errors[1]).toMatch(/properties is not valid JSON/);
    expect(res.errors[2]).toMatch(/properties must be a JSON object/);
  });

  it('normalises timestamps to ISO-8601 UTC', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'm', customer_id: 'c', quantity: '1', timestamp: '2026-09-07T10:00:00Z' },
      ])
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0].timestamp).toBe('2026-09-07T10:00:00.000Z');
  });

  it('rejects an unparseable timestamp instead of silently billing "now"', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'm', customer_id: 'c', quantity: '1', timestamp: '07/09/2026 banana' },
      ])
    );
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/timestamp "07\/09\/2026 banana" is not a valid date/);
  });
});

describe('parseBatchInput — row validation', () => {
  const row = (over: Record<string, unknown>) =>
    parseBatchInput(JSON.stringify([{ meter_code: 'm', customer_id: 'c', quantity: '1', ...over }]));

  it('requires meter_code', () => {
    const res = row({ meter_code: '  ' });
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/meter_code is required/);
  });

  it('requires customer_id', () => {
    const res = row({ customer_id: '' });
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/customer_id is required/);
  });

  it.each([
    ['missing', undefined],
    ['null', null],
    ['blank', '  '],
    ['zero', '0'],
    ['negative', '-5'],
    ['non-numeric', 'ten'],
  ])('rejects a %s quantity', (_label, quantity) => {
    const res = row({ quantity });
    expect(res.events).toHaveLength(0);
    expect(res.errors[0]).toMatch(/quantity must be a number greater than 0/);
  });

  it('collects every problem for a row into a single message', () => {
    const res = parseBatchInput(JSON.stringify([{ quantity: '0' }]));
    expect(res.errors).toHaveLength(1);
    expect(res.errors[0]).toBe(
      'Event 1: meter_code is required; customer_id is required; quantity must be a number greater than 0'
    );
  });

  it('keeps the valid rows when other rows fail', () => {
    const res = parseBatchInput(
      JSON.stringify([
        { meter_code: 'm', customer_id: 'c1', quantity: '1' },
        { meter_code: '', customer_id: 'c2', quantity: '2' },
        { meter_code: 'm', customer_id: 'c3', quantity: '3' },
      ])
    );
    expect(res.events.map((e) => e.customer_id)).toEqual(['c1', 'c3']);
    expect(res.errors).toHaveLength(1);
    expect(res.errors[0]).toMatch(/^Event 2: /);
  });
});

describe('parseBatchInput — CSV', () => {
  it('parses a header row plus data rows', () => {
    const res = parseBatchInput(
      ['meter_code,customer_id,quantity', 'api_calls,cus_1,10', 'api_calls,cus_2,2.5'].join('\n')
    );
    expect(res.format).toBe('csv');
    expect(res.errors).toEqual([]);
    expect(res.events).toHaveLength(2);
    expect(res.events[1]).toMatchObject({ customer_id: 'cus_2', quantity: '2.5' });
  });

  it('is case-insensitive about the header and tolerates CRLF and blank lines', () => {
    const res = parseBatchInput('Meter_Code,Customer_ID,Quantity\r\napi,cus_1,1\r\n\r\napi,cus_2,2\r\n');
    expect(res.errors).toEqual([]);
    expect(res.events).toHaveLength(2);
  });

  it('maps every documented CSV column', () => {
    const res = parseBatchInput(
      [
        BATCH_CSV_COLUMNS.join(','),
        'api,cus_1,10,key-1,sub_1,2026-09-07T10:00:00Z,"{""region"":""in""}"',
      ].join('\n')
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0]).toEqual({
      meter_code: 'api',
      customer_id: 'cus_1',
      quantity: '10',
      idempotency_key: 'key-1',
      subscription_id: 'sub_1',
      timestamp: '2026-09-07T10:00:00.000Z',
      properties: { region: 'in' },
    });
  });

  it('honours quoted fields containing commas', () => {
    const res = parseBatchInput(
      ['meter_code,customer_id,quantity,properties', 'api,cus_1,1,"{""note"":""a,b,c""}"'].join('\n')
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0].properties).toEqual({ note: 'a,b,c' });
  });

  it('unescapes doubled quotes inside a quoted field', () => {
    const res = parseBatchInput(
      ['meter_code,customer_id,quantity,idempotency_key', 'api,cus_1,1,"key ""x"", y"'].join('\n')
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0].idempotency_key).toBe('key "x", y');
  });

  it('treats blank optional cells as absent', () => {
    const res = parseBatchInput(
      ['meter_code,customer_id,quantity,subscription_id,timestamp,properties', 'api,cus_1,1,,,'].join('\n')
    );
    expect(res.errors).toEqual([]);
    expect(res.events[0]).toMatchObject({ subscription_id: null, timestamp: null, properties: null });
    expect(res.events[0].idempotency_key).toMatch(UUID_V4);
  });

  it('requires a header row and at least one data row', () => {
    const res = parseBatchInput('meter_code,customer_id,quantity');
    expect(res.format).toBe('csv');
    expect(res.events).toEqual([]);
    expect(res.errors).toEqual(['CSV needs a header row and at least one data row.']);
  });

  it('reports a header missing the required columns', () => {
    const res = parseBatchInput(['meter_code,quantity', 'api,10'].join('\n'));
    expect(res.errors[0]).toBe('CSV header must include meter_code, customer_id and quantity.');
  });

  it('labels row errors with the real file line number', () => {
    const res = parseBatchInput(
      ['meter_code,customer_id,quantity', 'api,cus_1,1', 'api,cus_2,0'].join('\n')
    );
    expect(res.events).toHaveLength(1);
    expect(res.errors[0]).toMatch(/^Row 3: /);
  });

  it('ignores unknown columns without mis-aligning the known ones', () => {
    const res = parseBatchInput(
      ['region,meter_code,notes,customer_id,quantity', 'in,api,hello,cus_1,7'].join('\n')
    );
    expect(res.events).toHaveLength(1);
    expect(res.events[0]).toMatchObject({ meter_code: 'api', customer_id: 'cus_1', quantity: '7' });
  });

  // BUG: the "Ignoring unknown CSV column(s)" notice is pushed onto `errors`,
  // and BatchImportModal.tsx:64 disables Import while `parsed.errors.length > 0`.
  // So a CSV exported with any extra column (region, notes, …) can never be
  // imported, even though the parser says it is ignoring it. It should be a
  // separate `warnings` list.
  // See src/pages/usage/usageUtils.ts:188 and src/pages/usage/BatchImportModal.tsx:64.
  it('should not treat an ignorable unknown column as a blocking error', () => {
    const res = parseBatchInput(['meter_code,customer_id,quantity,region', 'api,cus_1,7,in'].join('\n'));
    expect(res.events).toHaveLength(1);
    expect(res.errors).toEqual([]);
  });


  it('detects CSV vs JSON from the first character only', () => {
    expect(parseBatchInput('[]').format).toBe('json');
    expect(parseBatchInput('{"events":[]}').format).toBe('json');
    expect(parseBatchInput('meter_code,customer_id,quantity\napi,c,1').format).toBe('csv');
  });
});
