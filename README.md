# roleAutomatorRoles

Public library of Jamf API role and privilege mappings for [RoleAutomator](https://github.com/joshikavan92/RoleAutomator).

- **Source:** Fetched from [Jamf Developer Documentation](https://developer.jamf.com/jamf-pro/docs) (Classic API + Jamf Pro API privileges).
- **Updated:** Daily via GitHub Actions; you can also run **Actions → Refresh Jamf roles → Run workflow** to refresh now.
- **Consumed by:** RoleAutomator macOS app via `https://raw.githubusercontent.com/joshikavan92/roleAutomatorRoles/main/roles/jamf-roles.json`.

## Files

| File | Description |
|------|-------------|
| `roles/jamf-roles.json` | Full role database (created by first workflow run) |
| `roles/classic-api-roles.json` | Classic API only |
| `roles/jamf-pro-api-roles.json` | Jamf Pro API only |
| `roles/privilege-categories.json` | Privilege categories |

## Local run

```bash
pip install -r requirements.txt
python sync_roles.py
```

## License

MIT
