# Stage 5: Taxonomy Placement & Evolution — Specification

**Status:** Draft — placement rules exist; evolution mechanism underspecified
**Precision level:** Medium (placement checklists inherited; tree evolution process needs zoom-in)
**Dependencies:** Stage 4 (Excerpting) output. Requires base taxonomy trees.

---

## 1. Purpose

Place each excerpt into the correct leaf node of the correct science's taxonomy tree. When the existing tree doesn't have the right node, propose taxonomy changes. Manage cross-science routing.

---

## 2. Inherited Precision

| Rule set | Source document | Checklist IDs |
|----------|----------------|---------------|
| Non-negotiable placement rules | `2_atoms_and_excerpts/checklists_v0.4.md` | PLACE.P.1 – PLACE.P.6 |
| Solidifying indicators | `2_atoms_and_excerpts/checklists_v0.4.md` | PLACE.S.1 – PLACE.S.4 |
| Cross-science handling | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §8.6 | PLACE.X.1 – PLACE.X.4 |
| Taxonomy change log | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §11 | — |
| Taxonomy strictness | `2_atoms_and_excerpts/00_BINDING_DECISIONS_v0.3.16.md` §12 | — |

---

## 3. Base Taxonomy Trees

Each science has a base taxonomy tree provided by the user. The tree is a YAML file with hierarchical nodes:

```yaml
# Example: balagha_v0_4.yaml (202 nodes, 143 leaves)
balagha:
  maani:
    khabar:
      haqiqat_al_khabar:
        _leaf: true
      kayfiyyat_ilqaa_al_khabar:
        _leaf: true
      ...
    inshaa:
      ...
  bayan:
    tashbih:
      ...
  badi:
    ...
```

**Current state:**
- بلاغة: `balagha_v0_4` exists (202 nodes, 143 leaves) ✓
- صرف: **Not yet provided** (TODO-001)
- نحو: **Not yet provided** (TODO-001)
- إملاء: **Not yet provided** (TODO-001)

---

## 4. Placement Logic

### 4.1 Normal case: excerpt maps to existing leaf

The excerpt's `placed_at` field points to a leaf node in the appropriate science's tree.

**Validation (PLACE.P rules):**
- P.1: The target node must exist in the active taxonomy
- P.2: The target node must be a leaf (not a branch)
- P.3: The excerpt's core atoms must genuinely teach the topic defined by that node
- P.4: If the node already has excerpts from other passages, the new excerpt must be consistent (teaching the same topic, not a different interpretation of the node name)
- P.5: Placement must be specific — not a catch-all parent node when a more specific child exists
- P.6: General/introductory content follows the branch-level convention (BD §6)

### 4.2 Missing node: taxonomy change proposal

When an excerpt teaches a topic not represented in the current tree:

1. The system generates a `taxonomy_change` proposal:
```json
{
  "change_type": "add_leaf",
  "parent_path": "balagha/maani/khabar",
  "new_node_id": "aqsam_al_khabar",
  "new_node_title_ar": "أقسام الخبر",
  "justification": "Excerpt teaches classification of khabar types not covered by existing leaves",
  "triggered_by_excerpt": "EXC_042"
}
```

2. Valid change types: `add_leaf`, `add_branch`, `rename_node`, `move_node`, `split_node`

3. Changes are **proposed, not applied**. They accumulate in `taxonomy_changes.jsonl`.

4. At the end of a book, the user reviews all proposed changes and approves/rejects them.

5. Approved changes are applied to create a new taxonomy version (e.g., `balagha_v0_5`).

### 4.3 Cross-science routing

When an excerpt from a بلاغة book is classified as صرف:
- The excerpt's `science_classification` is `sarf`
- The excerpt must be placed in the صرف taxonomy tree (not the بلاغة tree)
- If the صرف tree doesn't exist yet, the excerpt is stored in a pending queue until the tree is available
- The book's registry entry tracks which sciences received excerpts

### 4.4 Unrelated excerpts

Excerpts classified as `unrelated` are stored in:
```
books/{book_id}/unrelated_excerpts/
```
They are NOT placed in any taxonomy tree. They are preserved for potential future use (e.g., if a new science is added later).

---

## 5. Taxonomy Evolution Rules

### 5.1 Cumulative growth

The taxonomy tree grows across books. Book A may add 5 leaves. Book B may add 3 more. The tree is never pruned automatically.

### 5.2 Version control

Each state of the tree is a version. Versions are immutable once sealed. Changes create new versions.

### 5.3 Consistency requirement

When a new node is added, all previously placed excerpts remain valid at their current nodes. A taxonomy change must never invalidate existing placements.

---

## 6. Output Artifacts

| File | Description |
|------|-------------|
| `taxonomy_changes.jsonl` | Proposed changes from this book |
| `placement_report.json` | Stats: excerpts per node, cross-science count, unrelated count |
| `taxonomy_{science}_v{N+1}.yaml` | Updated tree (after user approval) |

---

## 7. Open Questions (To Resolve During Zoom-In)

1. **Tree visualization:** How does the user review taxonomy changes? A diff view? A tree viewer?
2. **Merge conflicts:** If two books are processed simultaneously and both propose changes to the same branch, how are conflicts resolved?
3. **Node granularity:** When should a leaf be split into sub-leaves? What's the threshold (number of excerpts? topic diversity?)?
4. **Cross-book node reuse:** How does the system know that excerpt from Book A and excerpt from Book B should go to the same node? Matching by node ID? By semantic similarity?
