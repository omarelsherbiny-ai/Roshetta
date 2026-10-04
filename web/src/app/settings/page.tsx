// web/src/app/settings/page.tsx (route: /settings — sends to the account settings page)
import { redirect } from 'next/navigation';

export default function SettingsIndexPage() {
  redirect('/settings/account');
}
