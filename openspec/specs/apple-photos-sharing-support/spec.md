# apple-photos-sharing-support Specification

## Purpose

Make scan descriptions usable in Apple Photos while accurately documenting which Apple sharing products preserve captions and which expose separate social comments.

## Requirements

### Requirement: Populate Apple Photos import metadata
The tool SHALL populate the standard embedded caption and title fields used by Apple Photos and SHALL document how a user can confirm the imported caption in the Photos information panel before sharing photographs.

#### Scenario: Caption validation after library import
- **WHEN** a tagged JPEG is imported into Apple Photos
- **THEN** the documented validation workflow allows the user to confirm that its derived description appears as the photograph's library caption or title

### Requirement: Do not misrepresent Shared Album metadata support
The tool and its documentation SHALL state that Apple Photos Shared Albums expose comments as their user-visible descriptive text and do not convert embedded JPEG caption metadata into Shared Album comments.

#### Scenario: Tagged photo is evaluated for a Shared Album
- **WHEN** a user considers adding a tagged photograph to an Apple Photos Shared Album
- **THEN** the documentation explains that its embedded caption can remain separate from the Shared Album's visible comments

### Requirement: Document caption-preserving Apple sharing
The documentation SHALL distinguish Shared Albums from iCloud Shared Photo Library and identify iCloud Shared Photo Library as the Apple option when a group of eligible, trusted participants must view and edit synchronized captions.

#### Scenario: User requires synchronized captions
- **WHEN** a user needs other participants to view and edit the Photos caption itself
- **THEN** the documented workflow directs the user to evaluate iCloud Shared Photo Library and explains its participant, permission, and storage trade-offs
