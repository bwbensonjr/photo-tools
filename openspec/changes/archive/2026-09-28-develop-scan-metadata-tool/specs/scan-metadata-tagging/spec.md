# Spec Delta

## Purpose

Provide a safe command-line workflow that assigns deterministic, verifiable dates, ordering, descriptions, and keywords to scanned JPEG photographs organized in date-prefixed folders.

## ADDED Requirements

### Requirement: Discover date-named scan folders
The tool SHALL discover top-level folders whose names match `YYYY-MM-DD-description`, validate the calendar date and non-empty description suffix, and process JPEG files directly within those folders without recursively modifying unrelated files.

#### Scenario: Valid scan folder
- **WHEN** a top-level folder has a valid date prefix, a non-empty description suffix, and `.jpg` or `.jpeg` files
- **THEN** the tool includes those JPEG files in its plan and derives the folder date and description from the folder name

#### Scenario: Unsupported top-level entry
- **WHEN** a top-level folder does not follow the required naming convention or contains no supported photographs
- **THEN** the tool leaves the entry unchanged and reports why it was skipped

### Requirement: Preserve deterministic scan order
The tool SHALL sort folders sharing a date by folder name and sort photographs within each folder by filename, using those orders consistently across repeated runs.

#### Scenario: Multiple scanner batches in one folder
- **WHEN** filenames contain different scanner timestamp prefixes and numeric sequence suffixes
- **THEN** the plan orders the photographs by their complete filenames and produces the same order on every run

### Requirement: Prevent same-date interleaving
The tool SHALL allocate a single sequence of unique timestamps across all valid folders that share a date, beginning at the configured start time and advancing by the configured interval, so every folder occupies one contiguous time range and no two photographs in that date group receive the same timestamp.

#### Scenario: Three folders share a date
- **WHEN** three valid folders share one date
- **THEN** the second folder begins after the final timestamp assigned to the first folder and the third begins after the final timestamp assigned to the second folder

#### Scenario: A filtered run targets one same-date folder
- **WHEN** a user limits output or application to one folder that has valid same-date siblings
- **THEN** the tool calculates that folder's timestamps using the complete date group before filtering, preserving the same timestamps it would receive in an unfiltered run

#### Scenario: Sequence would cross midnight
- **WHEN** the configured start time and interval cannot fit a date group's photographs within that calendar date
- **THEN** the tool refuses to apply metadata and reports the affected date group

### Requirement: Derive descriptive metadata
The tool SHALL convert the portion of a valid folder name after the date prefix into a human-readable description by replacing separator hyphens with spaces, and SHALL use that text as the photograph's caption, title, and keyword value.

#### Scenario: Hyphenated folder description
- **WHEN** a folder is named `1997-03-06-In-the-woods`
- **THEN** every planned photograph in that folder has `In the woods` as its derived description

### Requirement: Write interoperable metadata
For each selected photograph, the tool SHALL write the planned capture timestamp to the documented EXIF and XMP date fields and write the derived text to the documented EXIF, IPTC, and XMP caption, title, and keyword fields without altering image pixels.

#### Scenario: Metadata application succeeds
- **WHEN** a user explicitly applies a valid plan and ExifTool completes successfully
- **THEN** each selected JPEG contains the planned timestamp and derived text in every required metadata field and its image payload remains unchanged

### Requirement: Default to a non-mutating plan
The tool SHALL default to dry-run behavior and SHALL require an explicit apply option before changing any photograph.

#### Scenario: Invocation without apply option
- **WHEN** a user runs the tool without the apply option
- **THEN** the tool prints the ordered folder, photograph, timestamp, and description plan and does not modify files

### Requirement: Control backups and scope
The tool SHALL allow users to select one or more folders, choose whether ExifTool backup files are retained, and resolve every write target beneath the selected scan root.

#### Scenario: Selected-folder application
- **WHEN** a user explicitly applies metadata with one or more folder filters
- **THEN** only supported JPEGs in those selected folders are modified

#### Scenario: Path escapes the scan root
- **WHEN** a discovered or selected write target resolves outside the scan root
- **THEN** the tool refuses the operation before invoking ExifTool

### Requirement: Verify applied metadata
After a write, the tool SHALL read the required metadata fields back from every selected photograph, compare them with the plan, report mismatches, and return a nonzero status when application or verification fails.

#### Scenario: Required field differs after write
- **WHEN** any required date, caption, title, or keyword field does not equal its planned value
- **THEN** the tool identifies the photograph and mismatched field and exits unsuccessfully

### Requirement: Protect source photographs during automated tests
The automated test suite SHALL operate only on generated fixtures or temporary copies and MUST NOT write to the user's scan collection.

#### Scenario: Test suite execution
- **WHEN** the repository test suite runs on a machine where the user's scan root exists
- **THEN** all source photographs under that root remain byte-for-byte unchanged
