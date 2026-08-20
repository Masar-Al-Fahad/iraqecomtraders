import { useEffect, useState } from 'react';
import { Archive, Download, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { financialErpApi } from '@/lib/financialErpApi';
import { client } from '@/lib/localApi';
import type { FinancialBackup } from '@/types/financialErp';
import { CompactTable, Empty, FormDialog, PageTitle, StatusBadge } from './FinancialUi';

type Props = { can: (key: string) => boolean; notify: (e: unknown) => void; success: (message: string) => void };
const size = (bytes: number) =>
  bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

export function BackupsPage({ can, notify, success }: Props) {
  const [rows, setRows] = useState<FinancialBackup[]>([]);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [restore, setRestore] = useState<FinancialBackup>();
  const [confirmation, setConfirmation] = useState('');
  const [restoreNotes, setRestoreNotes] = useState('');
  const [secretStatus, setSecretStatus] = useState<{
    configured: boolean;
    legacy_fallback_enabled: boolean;
    message: string;
  } | null>(null);
  const [newSecret, setNewSecret] = useState('');
  const [confirmSecret, setConfirmSecret] = useState('');

  const load = async () => {
    try {
      setRows((await financialErpApi.backups()).items);
    } catch (e) {
      notify(e);
    }
  };
  const loadSecretStatus = async () => {
    try {
      const st = await client.apiCall.invoke({
        url: '/api/v1/admin/financial/backups/restore-secret/status',
        method: 'GET',
        data: {},
      });
      setSecretStatus(st.data);
    } catch {
      setSecretStatus(null);
    }
  };
  useEffect(() => {
    void load();
    void loadSecretStatus();
  }, []);

  const create = async () => {
    setBusy(true);
    try {
      await financialErpApi.createBackup(notes);
      setNotes('');
      await load();
      success('تم إنشاء النسخة الاحتياطية وحفظها في التخزين الخاص');
    } catch (e) {
      notify(e);
    } finally {
      setBusy(false);
    }
  };

  const saveSecret = async () => {
    if (newSecret.trim().length < 6 || newSecret !== confirmSecret) {
      notify(new Error('أدخل رمزًا متطابقًا لا يقل عن 6 أحرف'));
      return;
    }
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/admin/financial/backups/restore-secret',
        method: 'PUT',
        data: { new_secret: newSecret.trim() },
      });
      setNewSecret('');
      setConfirmSecret('');
      await loadSecretStatus();
      success(res.data?.message || 'تم حفظ رمز التأكيد');
    } catch (e) {
      notify(e);
    }
  };

  const requestRestore = async () => {
    if (!restore) return;
    if (!restoreNotes.trim()) {
      notify(new Error('سبب الاستعادة مطلوب'));
      return;
    }
    if (!confirmation.trim()) {
      notify(new Error('رمز تأكيد الاستعادة مطلوب'));
      return;
    }
    try {
      await financialErpApi.requestRestore(restore.id, confirmation, restoreNotes);
      setRestore(undefined);
      setConfirmation('');
      setRestoreNotes('');
      await load();
      success('تم تسجيل طلب الاستعادة فقط — لم تُستبدل قاعدة البيانات. راجع عمود الحالة «طلب استعادة».');
    } catch (e) {
      notify(e);
    }
  };

  return (
    <div className="space-y-4">
      <PageTitle
        title="النسخ الاحتياطية"
        description="إنشاء النسخ يعمل داخل التطبيق. زر الاستعادة = طلب مراجعة فقط، وليس تنفيذ pg_restore داخل التطبيق."
      />
      <Card>
        <CardContent className="p-4 grid md:grid-cols-[1fr_auto] gap-3 items-end">
          <div>
            <Label>ملاحظات النسخة</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="سبب إنشاء النسخة أو وصفها" />
          </div>
          {can('backups.create') && (
            <Button type="button" disabled={busy} onClick={create}>
              <Plus className="w-4 h-4 ml-2" />
              {busy ? 'جاري الإنشاء...' : 'إنشاء نسخة احتياطية الآن'}
            </Button>
          )}
        </CardContent>
      </Card>

      {!secretStatus?.configured && (
        <Card>
          <CardContent className="p-4 text-sm text-amber-900 bg-amber-50 border border-amber-200">
            <p className="font-bold">رمز تأكيد الاستعادة غير مضبوط</p>
            <p className="mt-1">
              لن يُقبل أي طلب استعادة حتى يُعيَّن رمز من حساب يملك صلاحية «رمز تأكيد الاستعادة». لا يوجد رمز افتراضي مثل RESTORE.
            </p>
          </CardContent>
        </Card>
      )}

      {can('backups.manage_restore_secret') && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <h3 className="font-bold">رمز تأكيد طلب الاستعادة</h3>
            <p className="text-sm text-slate-600">
              {secretStatus?.message || 'يُخزَّن الرمز كـ hash فقط ولن يُعرض نصه بعد الحفظ. بدون رمز مضبوط لن يُقبل أي طلب استعادة.'}
            </p>
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <Label>الرمز الجديد</Label>
                <Input type="password" dir="ltr" value={newSecret} onChange={(e) => setNewSecret(e.target.value)} placeholder="رمز سري ≥ 6 أحرف" />
              </div>
              <div>
                <Label>تأكيد الرمز</Label>
                <Input type="password" dir="ltr" value={confirmSecret} onChange={(e) => setConfirmSecret(e.target.value)} />
              </div>
            </div>
            <Button type="button" variant="outline" onClick={() => void saveSecret()}>
              حفظ رمز التأكيد
            </Button>
          </CardContent>
        </Card>
      )}

      <CompactTable headers={['النسخة', 'النوع', 'التاريخ والمنشئ', 'الحجم', 'الحالة', 'الملاحظات', 'الإجراءات']}>
        {rows.map((row) => (
          <tr key={row.id} className="border-t">
            <td className="p-3 font-mono">
              {row.backup_number}
              <small className="block text-slate-400">{row.checksum_sha256.slice(0, 12)}…</small>
            </td>
            <td>{row.kind === 'pre_restore' ? 'قبل الاستعادة' : 'يدوية'}</td>
            <td>
              {new Date(row.created_at).toLocaleString('en-GB')}
              <small className="block">{row.created_by}</small>
            </td>
            <td>{size(row.size_bytes)}</td>
            <td>
              <StatusBadge value={row.status} />
              {row.status === 'restore_requested' && (
                <small className="block text-amber-800">
                  طلب بواسطة {row.restore_requested_by || '-'} ·{' '}
                  {row.restore_requested_at ? new Date(row.restore_requested_at).toLocaleString('en-GB') : ''}
                </small>
              )}
            </td>
            <td>{row.notes || '-'}</td>
            <td className="flex gap-1 py-2">
              {can('backups.download') && (
                <Button type="button" size="icon" variant="ghost" onClick={() => financialErpApi.downloadBackup(row.id, row.backup_number).catch(notify)}>
                  <Download className="w-4 h-4" />
                </Button>
              )}
              {can('backups.restore') && row.status === 'ready' && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (secretStatus && !secretStatus.configured) {
                      notify(new Error('عيّن رمز تأكيد الاستعادة أولًا من الإعدادات أعلاه قبل طلب الاستعادة.'));
                      return;
                    }
                    setRestore(row);
                  }}
                >
                  <RotateCcw className="w-4 h-4 ml-1" />
                  طلب استعادة
                </Button>
              )}
              {can('backups.delete') && (
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  onClick={async () => {
                    if (!confirm(`حذف النسخة ${row.backup_number}؟`)) return;
                    try {
                      await financialErpApi.deleteBackup(row.id);
                      await load();
                      success('تم حذف ملف النسخة مع الاحتفاظ بسجل التدقيق');
                    } catch (e) {
                      notify(e);
                    }
                  }}
                >
                  <Trash2 className="w-4 h-4 text-red-600" />
                </Button>
              )}
            </td>
          </tr>
        ))}
        {!rows.length && (
          <tr>
            <td colSpan={7}>
              <Empty title="لا توجد نسخ احتياطية" description="أنشئ أول نسخة من الزر أعلاه." />
            </td>
          </tr>
        )}
      </CompactTable>

      <Card>
        <CardContent className="p-4 space-y-2 text-sm text-amber-900 bg-amber-50">
          <div className="flex gap-3">
            <Archive className="w-5 h-5 shrink-0" />
            <div>
              <p className="font-bold">فلسفة الاستعادة</p>
              <p>طلب الاستعادة من التطبيق ليس استبدالًا فوريًا لقاعدة البيانات.</p>
              <ol className="list-decimal pr-5 mt-1 space-y-1">
                <li>التحقق من رمز التأكيد وسبب الاستعادة.</li>
                <li>إنشاء نسخة تلقائية pre_restore للحالة الحالية.</li>
                <li>تسجيل الطلب في Audit Log وحالة «طلب استعادة».</li>
                <li>التنفيذ الفعلي يبقى خارج التطبيق (DevOps / Railway / Supabase).</li>
              </ol>
            </div>
          </div>
        </CardContent>
      </Card>

      <FormDialog open={!!restore} onOpenChange={(open) => !open && setRestore(undefined)} title={`طلب استعادة ${restore?.backup_number || ''}`}>
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 space-y-2">
          <p>
            هذا <b>طلب مراجعة</b> وليس استعادة فورية لقاعدة البيانات.
          </p>
          <p>
            {secretStatus?.configured
              ? 'أدخل رمز تأكيد الاستعادة المضبوط من إعدادات هذه الصفحة (لن يُعرض الرمز المحفوظ).'
              : 'لم يُضبط رمز تأكيد الاستعادة بعد. أوقف وأعد الرمز من الإعدادات أعلاه أولًا — لا يوجد رمز افتراضي مثل RESTORE.'}
          </p>
        </div>
        <div>
          <Label>رمز التأكيد</Label>
          <Input
            dir="ltr"
            type="password"
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            placeholder="••••••"
            disabled={!secretStatus?.configured}
          />
        </div>
        <div>
          <Label>سبب الاستعادة (مطلوب)</Label>
          <Textarea value={restoreNotes} onChange={(e) => setRestoreNotes(e.target.value)} placeholder="مثال: استعادة بعد خطأ إدخال بتاريخ..." />
        </div>
        <Button
          type="button"
          variant="destructive"
          disabled={!secretStatus?.configured || !confirmation.trim() || !restoreNotes.trim()}
          onClick={requestRestore}
        >
          تسجيل طلب الاستعادة (بدون تنفيذ DB)
        </Button>
      </FormDialog>
    </div>
  );
}
