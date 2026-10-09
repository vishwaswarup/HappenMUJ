import { useMemo, useState, type FormEvent } from 'react';
import { api } from '../lib/api';
import { CATEGORIES, EVENT_TYPES, FEE_TYPES, PLATFORMS, TEAM_TYPES } from '../lib/constants';
import {
  DETAIL_FIELDS, getPath, linesToText, namesToText, pairsToText, setPath, textToLines, textToNames, textToPairs, type DetailField,
} from '../lib/eventDetails';
import { safeUrl } from '../lib/format';
import { navigate } from '../lib/router';
import { parseDateTimeLocalIST, toDateTimeLocalIST } from '../lib/time';
import type { Category, Club, DetailsBag, EventDetail, EventInput, EventType, FeeType, RegPlatform, TeamType } from '../lib/types';
import { useApp } from '../state/AppContext';
import { Button, Field } from '../components/ui';

function initialText(f: DetailField, details: DetailsBag): string {
  const v = getPath(details, f.key);
  switch (f.kind) {
    case 'lines': return linesToText(v);
    case 'names': return namesToText(v);
    case 'pairs': return f.pairKeys ? pairsToText(v, f.pairKeys) : '';
    case 'bool': return v ? '1' : '';
    default: return v === undefined || v === null ? '' : String(v);
  }
}

export function EventForm({ existing, clubs }: { existing?: EventDetail; clubs: Club[] }) {
  const { toast } = useApp();
  const [title, setTitle] = useState(existing?.title ?? '');
  const [oneLiner, setOneLiner] = useState(existing?.one_liner ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [clubId, setClubId] = useState(existing?.club.id ?? clubs[0]?.id ?? '');
  const [category, setCategory] = useState<Category>(existing?.category ?? 'technical');
  const [type, setType] = useState<EventType>(existing?.event_type ?? 'workshop');
  const [tags, setTags] = useState((existing?.tags ?? []).join(', '));
  const [start, setStart] = useState(toDateTimeLocalIST(existing?.schedule.start));
  const [end, setEnd] = useState(toDateTimeLocalIST(existing?.schedule.end));
  const [venue, setVenue] = useState(existing?.venue.name ?? '');
  const [building, setBuilding] = useState(existing?.venue.building ?? '');
  const [room, setRoom] = useState(existing?.venue.room ?? '');
  const [feeType, setFeeType] = useState<FeeType>(existing?.fee.type ?? 'not_specified');
  const [feeAmount, setFeeAmount] = useState(existing?.fee.amount != null ? String(existing.fee.amount) : '');
  const [teamType, setTeamType] = useState<TeamType>(existing?.team.type ?? 'not_specified');
  const [teamMin, setTeamMin] = useState(existing?.team.min != null ? String(existing.team.min) : '');
  const [teamMax, setTeamMax] = useState(existing?.team.max != null ? String(existing.team.max) : '');
  const [regRequired, setRegRequired] = useState(existing?.registration.required ?? true);
  const [platform, setPlatform] = useState<RegPlatform>(existing?.registration.platform ?? 'google_forms');
  const [regUrl, setRegUrl] = useState(existing?.registration.url ?? '');
  const [deadline, setDeadline] = useState(toDateTimeLocalIST(existing?.registration.deadline));
  const [contactName, setContactName] = useState(existing?.contact?.name ?? '');
  const [contactEmail, setContactEmail] = useState(existing?.contact?.email ?? '');
  const [poster, setPoster] = useState<File | null>(null);
  const [detailText, setDetailText] = useState<Record<string, string>>(() => {
    const o: Record<string, string> = {};
    for (const t of Object.keys(DETAIL_FIELDS) as EventType[]) for (const f of DETAIL_FIELDS[t]) o[`${t}:${f.key}`] = initialText(f, existing?.details ?? {});
    return o;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'draft' | 'submit' | null>(null);
  const fields = DETAIL_FIELDS[type];
  const editable = !existing || existing.status === 'draft' || existing.status === 'rejected' || existing.status === 'published' || existing.status === 'pending_review';
  const dt = useMemo(() => (key: string) => detailText[`${type}:${key}`] ?? '', [detailText, type]);
  const setDt = (key: string, v: string) => setDetailText((d) => ({ ...d, [`${type}:${key}`]: v }));

  const buildDetails = (): DetailsBag => {
    let bag: DetailsBag = {};
    for (const f of fields) {
      const t = dt(f.key);
      let v: unknown;
      switch (f.kind) {
        case 'lines': v = textToLines(t); break;
        case 'names': v = textToNames(t); break;
        case 'pairs': v = f.pairKeys ? textToPairs(t, f.pairKeys) : []; break;
        case 'bool': v = t === '1'; break;
        case 'number': v = t.trim() === '' ? null : Number(t); break;
        default: v = t.trim();
      }
      if (v === '' || v === null || (Array.isArray(v) && v.length === 0)) continue;
      bag = setPath(bag, f.key, v);
    }
    return bag;
  };

  const validate = (): EventInput | null => {
    const e: Record<string, string> = {};
    const s = parseDateTimeLocalIST(start);
    const en = parseDateTimeLocalIST(end);
    if (title.trim().length < 3) e.title = 'Give the event a title (at least 3 characters).';
    if (oneLiner.trim().length < 10) e.oneLiner = 'Add a one-line summary (at least 10 characters).';
    if (description.trim().length < 20) e.description = 'Describe the event in at least a couple of sentences.';
    if (!clubId) e.club = 'Choose the club hosting this event.';
    if (!s) e.start = 'Choose a start date and time.';
    if (!en) e.end = 'Choose an end date and time.';
    if (s && en && en.getTime() <= s.getTime()) e.end = 'The event must end after it starts.';
    if (!venue.trim()) e.venue = 'Where is it happening?';
    if ((feeType === 'fixed' || feeType === 'per_participant' || feeType === 'per_team') && !(Number(feeAmount) > 0)) e.fee = 'Enter the amount in rupees.';
    if (teamType === 'range') {
      if (!(Number(teamMin) >= 1) || !(Number(teamMax) >= Number(teamMin))) e.team = 'Enter a minimum of 1 or more and a maximum at least as large.';
    }
    if (teamType === 'fixed' && !(Number(teamMin) >= 1)) e.team = 'Enter the team size.';
    let dl: Date | null = null;
    if (regRequired) {
      if (!safeUrl(regUrl)) e.regUrl = 'Paste the full registration link, starting with https://';
      if (deadline) {
        dl = parseDateTimeLocalIST(deadline);
        if (!dl) e.deadline = 'That deadline is not a valid date.';
        else if (s && dl.getTime() > s.getTime()) e.deadline = 'The deadline should be before the event starts.';
      }
    }
    if (contactEmail && !/^\S+@\S+\.\S+$/.test(contactEmail)) e.contactEmail = 'Enter a valid email address.';
    setErrors(e);
    if (Object.keys(e).length || !s || !en) return null;
    return {
      title: title.trim(), one_liner: oneLiner.trim(), description: description.trim(), club_id: clubId, category, event_type: type,
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean).slice(0, 8),
      schedule: { start: s.toISOString(), end: en.toISOString() },
      venue: { name: venue.trim(), building: building.trim() || null, room: room.trim() || null },
      fee: { type: feeType, amount: ['fixed', 'per_participant', 'per_team'].includes(feeType) ? Number(feeAmount) : null, currency: 'INR' },
      team: { type: teamType, min: teamType === 'range' || teamType === 'fixed' ? Number(teamMin) : null, max: teamType === 'range' ? Number(teamMax) : teamType === 'fixed' ? Number(teamMin) : null },
      registration: { required: regRequired, platform: regRequired ? platform : null, url: regRequired ? safeUrl(regUrl) : null, deadline: regRequired && dl ? dl.toISOString() : null },
      contact: contactName.trim() && contactEmail.trim() ? { name: contactName.trim(), email: contactEmail.trim() } : null,
      details: buildDetails(),
    };
  };

  const run = async (submit: boolean, ev?: FormEvent) => {
    ev?.preventDefault();
    const input = validate();
    if (!input) {
      toast('Fix the highlighted fields first.', 'error');
      requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    setBusy(submit ? 'submit' : 'draft');
    try {
      let saved = existing ? await api.updateEvent(existing.id, input, poster) : await api.createEvent(input, poster);
      if (submit && saved.status !== 'pending_review' && saved.status !== 'published') saved = await api.submitEvent(saved.id);
      toast(submit ? 'Sent for review. An admin will look at it soon.' : 'Draft saved.', 'ok');
      navigate('/manage');
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Could not save the event.', 'error');
    } finally { setBusy(null); }
  };

  const err = (k: string) => errors[k];
  const inv = (k: string) => ({ 'aria-invalid': !!errors[k] || undefined, 'aria-describedby': errors[k] ? `${k}-err` : undefined });

  return (
    <form className="eform" onSubmit={(e) => run(false, e)} noValidate>
      <fieldset className="panel form" disabled={!editable}>
        <legend className="panel__title">The basics</legend>
        <Field id="title" label="Title" error={err('title')}><input id="title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} {...inv('title')} /></Field>
        <Field id="oneLiner" label="One-line summary" hint="Shown on cards. Keep it under about 100 characters." error={err('oneLiner')}><input id="oneLiner" value={oneLiner} maxLength={160} onChange={(e) => setOneLiner(e.target.value)} {...inv('oneLiner')} /></Field>
        <div className="form-row">
          <Field id="club" label="Hosting club" error={err('club')}>
            <select id="club" value={clubId} onChange={(e) => setClubId(e.target.value)} {...inv('club')}>{clubs.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          </Field>
          <Field id="category" label="Category"><select id="category" value={category} onChange={(e) => setCategory(e.target.value as Category)}>{CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
          <Field id="type" label="Event type" hint="Changes the extra details below."><select id="type" value={type} onChange={(e) => setType(e.target.value as EventType)}>{EVENT_TYPES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
        </div>
        <Field id="description" label="Description" error={err('description')}><textarea id="description" rows={6} value={description} onChange={(e) => setDescription(e.target.value)} {...inv('description')} /></Field>
        <Field id="tags" label="Tags" hint="Comma separated, up to 8."><input id="tags" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
        <Field id="poster" label="Poster image" hint="Optional. Events without one get a generated poster."><input id="poster" type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setPoster(e.target.files?.[0] ?? null)} /></Field>
      </fieldset>

      <fieldset className="panel form" disabled={!editable}>
        <legend className="panel__title">When and where (IST)</legend>
        <div className="form-row">
          <Field id="start" label="Starts" error={err('start')}><input id="start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} {...inv('start')} /></Field>
          <Field id="end" label="Ends" error={err('end')}><input id="end" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} {...inv('end')} /></Field>
        </div>
        <div className="form-row">
          <Field id="venue" label="Venue" error={err('venue')}><input id="venue" value={venue} onChange={(e) => setVenue(e.target.value)} {...inv('venue')} /></Field>
          <Field id="building" label="Building"><input id="building" value={building} onChange={(e) => setBuilding(e.target.value)} /></Field>
          <Field id="room" label="Room"><input id="room" value={room} onChange={(e) => setRoom(e.target.value)} /></Field>
        </div>
      </fieldset>

      <fieldset className="panel form" disabled={!editable}>
        <legend className="panel__title">Fee, team and registration</legend>
        <div className="form-row">
          <Field id="feeType" label="Fee"><select id="feeType" value={feeType} onChange={(e) => setFeeType(e.target.value as FeeType)}>{FEE_TYPES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
          {['fixed', 'per_participant', 'per_team'].includes(feeType) && <Field id="fee" label="Amount in ₹" error={err('fee')}><input id="fee" inputMode="numeric" value={feeAmount} onChange={(e) => setFeeAmount(e.target.value)} {...inv('fee')} /></Field>}
        </div>
        <div className="form-row">
          <Field id="teamType" label="Team size"><select id="teamType" value={teamType} onChange={(e) => setTeamType(e.target.value as TeamType)}>{TEAM_TYPES.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
          {(teamType === 'range' || teamType === 'fixed') && <Field id="team" label={teamType === 'range' ? 'Minimum' : 'Members'} error={err('team')}><input id="team" inputMode="numeric" value={teamMin} onChange={(e) => setTeamMin(e.target.value)} {...inv('team')} /></Field>}
          {teamType === 'range' && <Field id="teamMax" label="Maximum"><input id="teamMax" inputMode="numeric" value={teamMax} onChange={(e) => setTeamMax(e.target.value)} /></Field>}
        </div>
        <label className="check"><input type="checkbox" checked={regRequired} onChange={(e) => setRegRequired(e.target.checked)} /> Students must register on an external page</label>
        {regRequired && (
          <>
            <div className="form-row">
              <Field id="platform" label="Where"><select id="platform" value={platform} onChange={(e) => setPlatform(e.target.value as RegPlatform)}>{PLATFORMS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></Field>
              <Field id="deadline" label="Registration deadline" hint="Optional" error={err('deadline')}><input id="deadline" type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} {...inv('deadline')} /></Field>
            </div>
            <Field id="regUrl" label="Registration link" hint="HappenMUJ never collects registrations. Students are sent here." error={err('regUrl')}><input id="regUrl" type="url" value={regUrl} onChange={(e) => setRegUrl(e.target.value)} placeholder="https://" {...inv('regUrl')} /></Field>
          </>
        )}
        <div className="form-row">
          <Field id="cn" label="Contact name"><input id="cn" value={contactName} onChange={(e) => setContactName(e.target.value)} /></Field>
          <Field id="ce" label="Contact email" error={err('contactEmail')}><input id="ce" type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} {...inv('contactEmail')} /></Field>
        </div>
      </fieldset>

      <fieldset className="panel form" disabled={!editable}>
        <legend className="panel__title">{EVENT_TYPES.find((t) => t.id === type)?.label} details</legend>
        {fields.map((f) => {
          const id = `d-${f.key}`;
          const v = dt(f.key);
          if (f.kind === 'bool') return <label key={f.key} className="check"><input type="checkbox" checked={v === '1'} onChange={(e) => setDt(f.key, e.target.checked ? '1' : '')} /> {f.label}</label>;
          const multi = f.kind === 'lines' || f.kind === 'pairs' || f.kind === 'names' || f.kind === 'textarea';
          return (
            <Field key={f.key} id={id} label={f.label} hint={f.hint}>
              {multi ? <textarea id={id} rows={4} value={v} onChange={(e) => setDt(f.key, e.target.value)} /> : <input id={id} type={f.kind === 'number' ? 'number' : f.kind === 'date' ? 'date' : 'text'} value={v} onChange={(e) => setDt(f.key, e.target.value)} />}
            </Field>
          );
        })}
      </fieldset>

      <div className="form-actions form-actions--sticky">
        <Button type="submit" loading={busy === 'draft'} disabled={!editable || busy === 'submit'}>Save draft</Button>
        <Button variant="primary" loading={busy === 'submit'} disabled={!editable || busy === 'draft'} onClick={() => run(true)}>Save and send for review</Button>
        <Button variant="quiet" onClick={() => navigate('/manage')}>Cancel</Button>
      </div>
    </form>
  );
}
