export const sampleSupplierInputRows = [
  { record_id: 'SUP-001', vendor_name: 'Apple Inc', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-APPLE-001', spend_category: 'Technology' },
  { record_id: 'SUP-002', vendor_name: 'NVIDIA Corporation', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-NVIDIA-002', spend_category: 'Technology' },
  { record_id: 'SUP-003', vendor_name: 'Oracle America, Inc.', country: 'US', source_system: 'Procurement', submitted_identifier: 'DEMO-ORACLE-003', spend_category: 'Software' },
  { record_id: 'SUP-004', vendor_name: 'Adobe Inc.', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-ADOBE-004', spend_category: 'Software' },
  { record_id: 'SUP-005', vendor_name: 'Cisco Systems, Inc.', country: 'US', source_system: 'Procurement', submitted_identifier: 'DEMO-CISCO-005', spend_category: 'Network Equipment' },
  { record_id: 'SUP-006', vendor_name: 'Intel Corporation', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-INTEL-006', spend_category: 'Hardware' },
  { record_id: 'SUP-007', vendor_name: 'Dell Technologies Inc.', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-DELL-007', spend_category: 'Hardware' },
  { record_id: 'SUP-008', vendor_name: 'IBM Corporation', country: 'US', source_system: 'Procurement', submitted_identifier: 'DEMO-IBM-008', spend_category: 'Services' },
  { record_id: 'SUP-009', vendor_name: 'ServiceNow, Inc.', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-SNOW-009', spend_category: 'Software' },
  { record_id: 'SUP-010', vendor_name: 'Workday, Inc.', country: 'US', source_system: 'Procurement', submitted_identifier: 'DEMO-WDAY-010', spend_category: 'Software' },
  { record_id: 'SUP-011', vendor_name: 'Snowflake Inc.', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-SNOWFLAKE-011', spend_category: 'Cloud Data' },
  { record_id: 'SUP-012', vendor_name: 'CrowdStrike Holdings, Inc.', country: 'US', source_system: 'Security', submitted_identifier: 'DEMO-CRWD-012', spend_category: 'Security' },
  { record_id: 'SUP-013', vendor_name: 'Datadog, Inc.', country: 'US', source_system: 'Security', submitted_identifier: 'DEMO-DDOG-013', spend_category: 'Observability' },
  { record_id: 'SUP-014', vendor_name: 'Atlassian Corporation', country: 'AU', source_system: 'Procurement', submitted_identifier: 'DEMO-TEAM-014', spend_category: 'Software' },
  { record_id: 'SUP-015', vendor_name: 'Microsoft Corp.', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-MSFT-015', spend_category: 'Software' },
  { record_id: 'SUP-016', vendor_name: 'Meta Platforms LLC', country: 'US', source_system: 'Marketing', submitted_identifier: 'DEMO-META-016', spend_category: 'Advertising' },
  { record_id: 'SUP-017', vendor_name: 'Tesla Motors', country: 'US', source_system: 'Fleet', submitted_identifier: 'DEMO-TSLA-017', spend_category: 'Fleet' },
  { record_id: 'SUP-018', vendor_name: 'Salesforce.com Inc', country: 'US', source_system: 'CRM', submitted_identifier: 'DEMO-CRM-018', spend_category: 'Software' },
  { record_id: 'SUP-019', vendor_name: 'Global Freight Partners', country: 'US', source_system: 'Logistics', submitted_identifier: 'DEMO-GFP-019', spend_category: 'Logistics' },
  { record_id: 'SUP-020', vendor_name: 'Blue River Packaging', country: 'US', source_system: 'Procurement', submitted_identifier: 'DEMO-BRP-020', spend_category: 'Packaging' },
  { record_id: 'SUP-021', vendor_name: 'Acme Industrial Supply LLC', country: 'US', source_system: 'Plant Ops', submitted_identifier: 'DEMO-ACME-021', spend_category: 'Industrial Supplies' },
  { record_id: 'SUP-022', vendor_name: 'Northstar Components', country: 'CA', source_system: 'Plant Ops', submitted_identifier: 'DEMO-NORTHSTAR-022', spend_category: 'Components' },
  { record_id: 'SUP-023', vendor_name: 'AWS Marketplace', country: 'US', source_system: 'Cloud', submitted_identifier: 'DEMO-AWS-023', spend_category: 'Cloud Services' },
  { record_id: 'SUP-024', vendor_name: 'SAP America', country: 'US', source_system: 'ERP', submitted_identifier: 'DEMO-SAP-024', spend_category: 'Software' },
  { record_id: 'SUP-025', vendor_name: 'Unknown Vendor 4421', country: 'US', source_system: 'Manual Intake', submitted_identifier: 'DEMO-UNKNOWN-025', spend_category: 'Unclassified' },
];

export const sampleSupplierResolutions = [
  { record_id: 'SUP-001', input: 'Apple Inc', resolved: 'Apple Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-002', input: 'NVIDIA Corporation', resolved: 'NVIDIA Corporation', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-003', input: 'Oracle America, Inc.', resolved: 'Oracle America, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-004', input: 'Adobe Inc.', resolved: 'Adobe Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-005', input: 'Cisco Systems, Inc.', resolved: 'Cisco Systems, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-006', input: 'Intel Corporation', resolved: 'Intel Corporation', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-007', input: 'Dell Technologies Inc.', resolved: 'Dell Technologies Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-008', input: 'IBM Corporation', resolved: 'IBM Corporation', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-009', input: 'ServiceNow, Inc.', resolved: 'ServiceNow, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-010', input: 'Workday, Inc.', resolved: 'Workday, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-011', input: 'Snowflake Inc.', resolved: 'Snowflake Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-012', input: 'CrowdStrike Holdings, Inc.', resolved: 'CrowdStrike Holdings, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-013', input: 'Datadog, Inc.', resolved: 'Datadog, Inc.', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-014', input: 'Atlassian Corporation', resolved: 'Atlassian Corporation', layer: 'L1 exact', confidence: 1, reason: 'Exact canonical match' },
  { record_id: 'SUP-015', input: 'Microsoft Corp.', resolved: 'Microsoft Corporation', layer: 'L1 normalized', confidence: 0.99, reason: 'Corporate suffix normalization' },
  { record_id: 'SUP-016', input: 'Meta Platforms LLC', resolved: 'Meta Platforms, Inc.', layer: 'L1 normalized', confidence: 0.99, reason: 'Corporate suffix normalization' },
  { record_id: 'SUP-017', input: 'Tesla Motors', resolved: 'Tesla, Inc.', layer: 'L1 normalized', confidence: 0.98, reason: 'Known alias normalization' },
  { record_id: 'SUP-018', input: 'Salesforce.com Inc', resolved: 'Salesforce, Inc.', layer: 'L1 normalized', confidence: 0.99, reason: 'Punctuation and suffix normalization' },
  { record_id: 'SUP-019', input: 'Global Freight Partners', resolved: 'Global Freight Partners LLC', layer: 'L1 normalized', confidence: 0.98, reason: 'Suffix normalization' },
  { record_id: 'SUP-020', input: 'Blue River Packaging', resolved: 'Blue River Packaging Co.', layer: 'L1 normalized', confidence: 0.97, reason: 'Suffix normalization' },
  { record_id: 'SUP-021', input: 'Acme Industrial Supply LLC', resolved: 'Acme Industrial Supply, LLC', layer: 'L2 vector fuzzy', confidence: 0.94, reason: 'Near duplicate punctuation match' },
  { record_id: 'SUP-022', input: 'Northstar Components', resolved: 'Northstar Components, Inc.', layer: 'L2 vector fuzzy', confidence: 0.91, reason: 'High similarity supplier name' },
  { record_id: 'SUP-023', input: 'AWS Marketplace', resolved: 'Amazon Web Services, Inc.', layer: 'L2 vector fuzzy', confidence: 0.92, reason: 'Known marketplace alias' },
  { record_id: 'SUP-024', input: 'SAP America', resolved: 'SAP America, Inc.', layer: 'L2 vector fuzzy', confidence: 0.91, reason: 'High similarity supplier name' },
  { record_id: 'SUP-025', input: 'Unknown Vendor 4421', resolved: 'Human review required', layer: 'L4 review', confidence: 0.62, reason: 'No reliable canonical match' },
];

const sampleSupplierCsvHeaders = [
  'record_id',
  'vendor_name',
  'country',
  'source_system',
  'submitted_identifier',
  'spend_category',
];

const escapeCsvValue = (value) => {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

export const sampleSupplierCsv = [
  sampleSupplierCsvHeaders.join(','),
  ...sampleSupplierInputRows.map((row) => (
    sampleSupplierCsvHeaders.map((header) => escapeCsvValue(row[header])).join(',')
  )),
].join('\n');
