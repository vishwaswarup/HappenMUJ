import { DEFAULT_RANKING } from '../constants';
import { feeDisplay, registrationOpen, teamDisplay } from '../rules';
import { addDaysIST, dayKeyIST, istDate, istWall, startOfDayIST, MS } from '../time';
import type {
  Category, Club, CommentData, DetailsBag, EventDetail, EventStatus, EventType, FeeType, Post, PostScopeType,
  ReactionKind, RegPlatform, Role, TeamType, User,
} from '../types';

// Sample campus data. Everything is generated relative to "now" (in IST) so that every home section
// (today, tomorrow, next 7 days, top 10) is populated whenever the app is opened.

export interface MockEvent extends EventDetail {
  club_id: string;
  created_by: string;
  win: { saves: number; views: number; registration_clicks: number };
  featured_at: string | null;
}
export interface StoredUser extends User { password: string }
export interface StoredComment extends CommentData {}
export interface StoredPost extends Omit<Post, 'recent_comments' | 'my_reaction'> {}

export interface Seed {
  clubs: Club[];
  users: StoredUser[];
  events: MockEvent[];
  posts: StoredPost[];
  comments: StoredComment[];
  saved: Record<string, { event_id: string; status: 'saved' | 'registration_initiated'; saved_at: string }[]>;
  reactions: Record<string, ReactionKind>;
  ranking: typeof DEFAULT_RANKING;
}

const CLUBS: [string, string, string, Category, string][] = [
  ['c-acm', 'ACM', 'acm', 'technical', 'Coding, AI and open-source sessions.'],
  ['c-ieee', 'IEEE', 'ieee', 'technical', 'Electronics, hardware and hackathons.'],
  ['c-litmus', 'LITMUS', 'litmus', 'debating', 'Debates, quizzes and MUN preparation.'],
  ['c-tmc', 'TMC', 'tmc', 'cultural', 'Open mics and live evenings.'],
  ['c-aura', 'AURA', 'aura', 'cultural', 'Music, dance and campus socials.'],
  ['c-ecell', 'E-Cell', 'e-cell', 'career', 'Startup events and career workshops.'],
  ['c-sports', 'Sports Committee', 'sports-committee', 'sports', 'Inter-department and inter-college fixtures.'],
  ['c-aws', 'AWS Cloud Club', 'aws-cloud-club', 'technical', 'Cloud study jams and security talks.'],
  ['c-robotics', 'Robotics Club', 'robotics-club', 'technical', 'ROS, drones and open lab days.'],
  ['c-photo', 'Photography Club', 'photography-club', 'cultural', 'Photowalks, editing sessions and exhibitions.'],
  ['c-cse', 'School of Computer Science', 'school-of-cs', 'academic', 'Seminars and guest lectures.'],
  ['c-gaming', 'Gaming Guild', 'gaming-guild', 'gaming', 'Esports tournaments on campus.'],
];
const PENDING_CLUBS: [string, string, string, Category, string, string][] = [
  ['c-chess', 'Chess Club', 'chess-club', 'sports', 'Weekly games and a yearly open.', 'u-sana'],
  ['c-film', 'Film Society', 'film-society', 'cultural', 'Screenings and discussion nights.', 'u-meghna'],
];

type RegDeadline = { before: number } | { fromNow: number } | null;
interface Def {
  id: string; club: string; title: string; one: string; desc: string;
  cat: Category; type: EventType; d: number; at: string; dur: number; venue: [string, string];
  fee: [FeeType, number?]; team: [TeamType, number?, number?];
  reg: [RegPlatform, RegDeadline] | null; tags: string[]; details: DetailsBag; pop: number;
  status?: EventStatus; featured?: number; cancel?: string; reject?: string; by?: string; fromNowMin?: number;
}

const speaker = (name: string, bio = '') => ({ name, bio });
const prize = (rank: string, reward: string) => ({ rank, reward });

const DEFS: Def[] = [
  { id: 'e01', club: 'c-ieee', title: 'GenAI Hackathon 24', cat: 'hackathon', type: 'hackathon', d: 9, at: '10:00', dur: 24,
    venue: ['Innovation Lab', 'AB1'], fee: ['per_team', 499], team: ['range', 2, 4], reg: ['devfolio', { before: 48 }],
    one: 'Build a working prototype with open models in 24 hours. Teams of two to four, mentors on site, demos on Sunday morning.',
    desc: 'Twenty-four hours, one problem statement per track, and a panel that scores working demos over slides. Mentors from the IEEE student branch and faculty will be in the lab through the night. Bring a laptop, a charger and a team of two to four. Sleeping space is not provided, but the lab stays open.',
    tags: ['AI', 'GenAI', 'Hackathon', 'Open source'], pop: 95, featured: 30,
    details: { themes: ['Healthcare', 'Campus tools', 'Accessibility'], tracks: ['Open innovation', 'Best use of open-weight models'], duration_hours: 24, prizes: ['First: ₹25,000', 'Second: ₹15,000', 'Third: ₹10,000'], max_teams: 60 } },
  { id: 'e02', club: 'c-acm', title: 'AI/ML Workshop: From Data to Model', cat: 'technical', type: 'workshop', d: 1, at: '16:00', dur: 2,
    venue: ['AB3 Seminar Hall', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 16 }],
    one: 'Clean a real dataset, train a first model and learn to read its mistakes. Two hours, hands on, Python basics assumed.',
    desc: 'You will take a messy campus survey dataset, clean it, train a simple classifier and then spend half the session understanding where it fails. Expect to write code throughout. Seats are limited to the size of the hall, so register early.',
    tags: ['AI', 'Machine Learning', 'Workshop', 'Python'], pop: 80,
    details: { speaker: speaker('Dr. Meera Iyer', 'Associate professor, School of Computer Science'), topics: ['Cleaning a messy dataset', 'Training and validating a first model', 'Reading a confusion matrix'], duration_minutes: 120, prerequisites: ['Basic Python'], bring_own_laptop: true } },
  { id: 'e03', club: 'c-aura', title: 'Battle of Bands', cat: 'cultural', type: 'cultural_show', d: 1, at: '19:00', dur: 3,
    venue: ['Central Lawn', 'Campus'], fee: ['per_team', 100], team: ['range', 3, 6], reg: ['google_forms', { before: 20 }],
    one: 'Six bands play 15-minute sets on the lawn. Registration is for bands; the audience can walk in.',
    desc: 'Six shortlisted bands each get a 15-minute set, then the top two play a final song. Sound check is separate and starts at 5:30 PM. Audience entry is free and open to all MUJ students with an ID card.',
    tags: ['Music', 'Live', 'Bands', 'Cultural'], pop: 90, featured: 2,
    details: { performances: [{ title: 'Opening act', performer: 'AURA house band' }, { title: 'Heats', performer: 'Six registered bands, 15 minutes each' }, { title: 'Final set', performer: 'Top two bands' }], artists: ['AURA house band'], auditions_required: true, audition_date: '' } },
  { id: 'e04', club: 'c-sports', title: 'Inter-Department Football Cup', cat: 'sports', type: 'sports_match', d: 3, at: '07:00', dur: 5,
    venue: ['Football Ground', 'Sports Complex'], fee: ['free'], team: ['range', 11, 16], reg: ['google_forms', { before: 48 }],
    one: 'Knockout football between departments. Squads of 11 to 16, 25-minute halves, quarter-finals and semi-finals on one morning.',
    desc: 'Each department sends one squad. Fixtures are drawn at the briefing, which is part of the registration confirmation message. Bring studs and a department shirt in a single colour.',
    tags: ['Football', 'Inter-department', 'Knockout'], pop: 70,
    details: { sport: 'Football', match_type: 'Knockout', format: '11-a-side, 25-minute halves', teams: [{ name: 'Computer Science' }, { name: 'Mechanical' }, { name: 'Civil' }, { name: 'Electronics' }, { name: 'Architecture' }, { name: 'Management' }] } },
  { id: 'e05', club: 'c-litmus', title: 'Parliamentary Debate: Open House', cat: 'debating', type: 'competition', d: 4, at: '15:00', dur: 3,
    venue: ['Seminar Hall 2', 'AB2'], fee: ['free'], team: ['fixed', 2, 2], reg: ['google_forms', { before: 24 }],
    one: 'Pairs argue assigned motions in the British Parliamentary format. First-timers are welcome; a short briefing opens the session.',
    desc: 'Motions are released 15 minutes before each round. Judges give written feedback to every speaker, not only to the finalists. If you have never debated before, come for the briefing at 3:00 PM sharp.',
    tags: ['Debate', 'Public speaking', 'Parliamentary'], pop: 55,
    details: { prizes: [prize('Winners', 'Certificates and a book voucher')], eligibility: 'Open to all undergraduate students', rounds: [{ name: 'Round 1', description: 'Motions announced 15 minutes before' }, { name: 'Final', description: 'Top four speakers' }], judging_criteria: ['Argument structure', 'Rebuttal', 'Delivery'] } },
  { id: 'e06', club: 'c-ecell', title: 'Startup Pitch Night', cat: 'career', type: 'competition', d: 5, at: '17:00', dur: 3,
    venue: ['Main Auditorium', 'Main Block'], fee: ['not_specified'], team: ['range', 1, 3], reg: ['google_forms', { before: 36 }],
    one: 'Pitch an idea in four minutes to a panel of alumni founders. Teams of one to three; no prototype required.',
    desc: 'Each team gets four minutes to pitch and three minutes of questions. The panel is made up of alumni who have started companies. The winning team gets a mentoring session; everyone gets written feedback.',
    tags: ['Startups', 'Pitching', 'Entrepreneurship'], pop: 65,
    details: { prizes: [prize('Winner', 'Mentoring session with an alumni founder')], eligibility: 'Any MUJ student with an idea or early prototype', rounds: [{ name: 'Pitch', description: 'Four minutes plus three minutes of questions' }], judging_criteria: ['Problem clarity', 'Market size', 'Team'] } },
  { id: 'e07', club: 'c-aws', title: 'AWS Cloud Practitioner Study Jam', cat: 'technical', type: 'workshop', d: 2, at: '14:00', dur: 3,
    venue: ['Computer Lab 3', 'AB2'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'Work through the Cloud Practitioner exam guide with peer mentors and practice questions. Bring a laptop.',
    desc: 'A guided pass through the four exam domains with timed practice questions after each. Mentors have all passed the exam in the last year. You do not need an AWS account for the session.',
    tags: ['Cloud', 'AWS', 'Certification'], pop: 60,
    details: { speaker: speaker('AWS Cloud Club mentors'), topics: ['Core services', 'Billing and pricing', 'Shared responsibility model'], duration_minutes: 180, prerequisites: [], bring_own_laptop: true } },
  { id: 'e08', club: 'c-robotics', title: 'Introduction to ROS 2', cat: 'technical', type: 'workshop', d: 6, at: '11:00', dur: 3,
    venue: ['Robotics Lab', 'AB2'], fee: ['per_participant', 150], team: ['individual'], reg: ['google_forms', { before: 48 }],
    one: 'Write your first ROS 2 nodes and drive a simulated robot. Three hours, laptop required, Python or C++ basics assumed.',
    desc: 'You will publish and subscribe to topics, launch a simulated differential-drive robot and plot its sensor data. The fee covers a pre-configured virtual machine image so that setup does not eat the session.',
    tags: ['Robotics', 'ROS 2', 'Python'], pop: 58,
    details: { speaker: speaker('Robotics Club core team'), topics: ['Nodes and topics', 'Simulating a differential-drive robot', 'Visualising sensor data'], duration_minutes: 180, prerequisites: ['Python or C++ basics'], bring_own_laptop: true } },
  { id: 'e09', club: 'c-tmc', title: 'Open Mic Night', cat: 'cultural', type: 'cultural_show', d: 2, at: '18:30', dur: 2.5,
    venue: ['Central Lawn', 'Campus'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Songs, poems and stand-up from anyone who signs up at the door. No online registration; the list opens at 6 PM.',
    desc: 'Each act gets up to six minutes. Names go on the list at the venue from 6:00 PM, in order of arrival. Acoustic instruments only; a small sound system is provided for vocals.',
    tags: ['Music', 'Poetry', 'Open mic'], pop: 52,
    details: { performances: [{ title: 'Sign-up', performer: 'Names go on the list at the venue from 6:00 PM' }], artists: [], auditions_required: false } },
  { id: 'e10', club: 'c-cse', title: 'Research Paper Writing Seminar', cat: 'academic', type: 'seminar', d: 3, at: '11:30', dur: 1.5,
    venue: ['Seminar Hall 1', 'AB3'], fee: ['free'], team: ['not_applicable'], reg: ['google_forms', { before: 24 }],
    one: 'How to get from a first draft to a conference submission: structure, figures, and replying to reviewers.',
    desc: 'A practical session for final-year students and anyone planning a paper this semester. The speaker will walk through a real accepted paper and its review thread.',
    tags: ['Research', 'Writing', 'Academic'], pop: 35,
    details: { speaker: speaker('Prof. Arvind Rao', 'School of Computer Science'), topic: 'Structuring a conference paper from first draft to submission', q_and_a_enabled: true } },
  { id: 'e11', club: 'c-photo', title: 'Campus Photowalk', cat: 'social', type: 'social', d: 8, at: '06:30', dur: 3,
    venue: ['Main Gate', 'Campus'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'An early walk around campus in morning light. Any camera or phone works. We end with chai at the canteen.',
    desc: 'We walk about three kilometres at an easy pace and stop wherever the light is good. Beginners are welcome; members will share quick tips on framing as you go.',
    tags: ['Photography', 'Outdoors'], pop: 40,
    details: { extra: { notes: 'Any camera or phone works. Wear shoes you can walk in.' } } },
  { id: 'e12', club: 'c-gaming', title: 'Valorant Campus Showdown', cat: 'gaming', type: 'competition', d: 10, at: '15:00', dur: 6,
    venue: ['Gaming Arena', 'Library Block'], fee: ['per_team', 250], team: ['fixed', 5, 5], reg: ['unstop', { before: 72 }],
    one: 'Five-a-side Valorant on campus machines. Group stage on Saturday afternoon, best-of-three playoffs in the evening.',
    desc: 'Teams of five plus one substitute. Machines and peripherals are provided; bring your own headset. Check-in closes 30 minutes before the first match.',
    tags: ['Valorant', 'Esports', 'Gaming'], pop: 72,
    details: { prizes: [prize('First', '₹6,000'), prize('Second', '₹3,000')], eligibility: 'MUJ students only; teams of five plus one substitute', rounds: [{ name: 'Group stage', description: 'Best of one' }, { name: 'Playoffs', description: 'Best of three' }], judging_criteria: [] } },
  { id: 'e13', club: 'c-sports', title: 'Chess Open Tournament', cat: 'sports', type: 'competition', d: 12, at: '10:00', dur: 6,
    venue: ['Indoor Games Hall', 'Sports Complex'], fee: ['per_participant', 50], team: ['individual'], reg: ['google_forms', { before: 72 }],
    one: 'Five Swiss rounds, 15 minutes per side. Boards and clocks are provided; bring your own score sheet if you have one.',
    desc: 'Open to all students at any rating. Pairings are posted on the notice board outside the hall before each round. The fee covers boards, clocks and certificates.',
    tags: ['Chess', 'Tournament'], pop: 33,
    details: { prizes: [prize('Top three', 'Medals and certificates')], eligibility: 'Open to all', rounds: [{ name: 'Swiss rounds', description: 'Five rounds, 15 minutes per side' }], judging_criteria: [] } },
  { id: 'e14', club: 'c-ecell', title: 'Resume Clinic', cat: 'career', type: 'workshop', d: 1, at: '11:00', dur: 2,
    venue: ['Placement Cell', 'Main Block'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 14 }],
    one: 'Bring a printed resume and get line-by-line feedback from final-year students who have been through placements.',
    desc: 'Small groups of four, twenty minutes per resume. You will leave with a marked-up copy and a checklist for the next version. Bring a printout, not a laptop.',
    tags: ['Careers', 'Resume', 'Placements'], pop: 62,
    details: { speaker: speaker('E-Cell placement mentors'), topics: ['One-page structure', 'Writing project bullets', 'What recruiters skim for'], duration_minutes: 120, prerequisites: ['A printed resume'], bring_own_laptop: false } },
  { id: 'e15', club: 'c-acm', title: 'Linux Install Fest', cat: 'technical', type: 'workshop', d: 7, at: '15:00', dur: 3,
    venue: ['Computer Lab 1', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'Dual-boot Linux on your own laptop with volunteers beside you. Back up your files first.',
    desc: 'Volunteers will help you pick a distribution, partition safely and set up a working terminal. The session ends with a short tour of package managers and shell basics.',
    tags: ['Linux', 'Open source'], pop: 38,
    details: { speaker: speaker('ACM volunteers'), topics: ['Dual boot safely', 'Package managers', 'Terminal basics'], duration_minutes: 180, prerequisites: ['Back up your data first'], bring_own_laptop: true } },
  { id: 'e16', club: 'c-ieee', title: 'Circuit Design Contest', cat: 'technical', type: 'competition', d: 11, at: '10:00', dur: 5,
    venue: ['Electronics Lab', 'AB1'], fee: ['per_team', 200], team: ['range', 2, 3], reg: ['google_forms', { before: 72 }],
    one: 'Design a circuit on paper, then build it on a breadboard. Two hours of design, three hours of build.',
    desc: 'A problem sheet is handed out at the start. Teams design on paper for two hours and then build and test on a breadboard. Components are provided; bring your own multimeter if you have one.',
    tags: ['Electronics', 'Circuits', 'Contest'], pop: 45,
    details: { prizes: [prize('Winners', 'Component kits')], eligibility: 'First- and second-year students', rounds: [{ name: 'Design', description: 'Two hours on paper' }, { name: 'Build', description: 'Three hours on a breadboard' }], judging_criteria: ['Correctness', 'Efficiency', 'Neatness of build'] } },
  { id: 'e17', club: 'c-ieee', title: 'Guest Lecture: Edge Computing', cat: 'academic', type: 'seminar', d: 5, at: '12:00', dur: 1.5,
    venue: ['Auditorium Annex', 'Main Block'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'An embedded-systems researcher on running models on small devices. Open to everyone; no registration needed.',
    desc: 'The talk covers memory and power limits on edge hardware and how teams trim models to fit. Slides will be shared by the IEEE student branch after the session.',
    tags: ['Edge computing', 'IoT', 'Guest lecture'], pop: 30,
    details: { speaker: speaker('Dr. Sunita Rathore', 'Industry researcher, embedded systems'), topic: 'Running machine-learning models on small devices', q_and_a_enabled: true } },
  { id: 'e18', club: 'c-litmus', title: 'Quiz Night', cat: 'social', type: 'competition', d: 2, at: '17:00', dur: 2.5,
    venue: ['Seminar Hall 2', 'AB2'], fee: ['free'], team: ['range', 2, 4], reg: ['google_forms', { fromNow: -6 }],
    one: 'General-knowledge quiz for teams of two to four. A written round, then a buzzer round for the top four teams.',
    desc: 'Thirty written questions across history, science, sport and campus trivia. The top four teams move to a buzzer round. Registration has closed; spectators can still watch from the back of the hall.',
    tags: ['Quiz', 'General knowledge'], pop: 48,
    details: { prizes: [prize('Winners', 'Vouchers for the campus café')], eligibility: 'Open to all', rounds: [{ name: 'Written round', description: '30 questions' }, { name: 'Buzzer round', description: 'Top four teams' }], judging_criteria: [] } },
  { id: 'e19', club: 'c-aura', title: 'Freshers’ Mixer', cat: 'social', type: 'social', d: 4, at: '18:00', dur: 3,
    venue: ['Central Lawn', 'Campus'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Games, music and club stalls on the lawn. Come as you are; no registration needed.',
    desc: 'More than a dozen clubs will have stalls, and AURA will run team games every half hour. Wear something you can sit on the grass in.',
    tags: ['Freshers', 'Social'], pop: 62,
    details: { extra: { notes: 'Wear something you can sit on the grass in.' } } },
  { id: 'e20', club: 'c-sports', title: 'Inter-College Cricket Series', cat: 'sports', type: 'sports_match', d: 14, at: '08:00', dur: 8,
    venue: ['Cricket Ground', 'Sports Complex'], fee: ['per_team', 1500], team: ['range', 11, 15], reg: ['website', { before: 168 }],
    one: 'Eight teams, T20 format, league stage over one Saturday. Squads of 11 to 15; the fee is per team.',
    desc: 'The league stage runs from 8:00 AM with four matches. The top two teams advance to a final the following weekend. Umpires and balls are provided by the Sports Committee.',
    tags: ['Cricket', 'Inter-college'], pop: 66,
    details: { sport: 'Cricket', match_type: 'League', format: 'T20, eight teams', teams: [{ name: 'MUJ A' }, { name: 'MUJ B' }] } },
  { id: 'e21', club: 'c-ecell', title: 'Design Thinking Bootcamp', cat: 'workshop', type: 'workshop', d: 10, at: '10:00', dur: 5,
    venue: ['Seminar Hall 1', 'AB3'], fee: ['fixed', 300], team: ['individual'], reg: ['google_forms', { before: 72 }],
    one: 'Interview real users, frame the problem and prototype on paper in one day. Lunch is included in the fee.',
    desc: 'You will work in assigned groups on a campus problem, run three short user interviews and finish with a paper prototype tested by another group.',
    tags: ['Design thinking', 'Startups', 'Workshop'], pop: 42,
    details: { speaker: speaker('E-Cell mentors', 'Alumni working in product roles'), topics: ['Interviewing users', 'Framing the problem', 'Prototyping on paper'], duration_minutes: 300, prerequisites: [], bring_own_laptop: false } },
  { id: 'e22', club: 'c-aws', title: 'Cloud Security Talk', cat: 'seminar', type: 'seminar', d: 12, at: '16:00', dur: 1.5,
    venue: ['Seminar Hall 2', 'AB2'], fee: ['free'], team: ['not_applicable'], reg: ['google_forms', { before: 24 }],
    one: 'An alumnus on the misconfigurations that cause most cloud breaches, and how to catch them before launch.',
    desc: 'Real, anonymised incidents and the one-line settings that would have prevented them. Includes a short checklist you can apply to your own projects.',
    tags: ['Cloud', 'Security'], pop: 28,
    details: { speaker: speaker('Karan Malhotra', 'Cloud security engineer, MUJ alumnus'), topic: 'Common misconfigurations and how to catch them', q_and_a_enabled: true } },
  { id: 'e23', club: 'c-robotics', title: 'Drone Racing Demo', cat: 'technical', type: 'competition', d: 16, at: '14:00', dur: 3,
    venue: ['Football Ground', 'Sports Complex'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 72 }],
    one: 'Time trials on a marked course for pilots who have flown FPV before. Spectators welcome.',
    desc: 'Pilots fly three laps and the best lap counts. Bring your own drone and goggles; batteries can be charged at the Robotics Club desk.',
    tags: ['Drones', 'FPV', 'Robotics'], pop: 54,
    details: { prizes: [prize('Fastest lap', 'A trophy')], eligibility: 'Pilots must have flown FPV before', rounds: [{ name: 'Time trial', description: 'Three laps, best lap counts' }], judging_criteria: ['Lap time'] } },
  { id: 'e24', club: 'c-aura', title: 'Dance Showcase', cat: 'cultural', type: 'cultural_show', d: 13, at: '18:00', dur: 3,
    venue: ['Main Auditorium', 'Main Block'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Classical, contemporary and folk performances from student groups. Entry is free for MUJ students.',
    desc: 'Eight performances across three hours with a short break. Doors open at 5:30 PM and seating is first come, first served.',
    tags: ['Dance', 'Showcase'], pop: 50,
    details: { performances: [{ title: 'Classical', performer: 'Kathak ensemble' }, { title: 'Contemporary', performer: 'AURA Dance Crew' }], artists: ['AURA Dance Crew'], auditions_required: false } },
  { id: 'e25', club: 'c-litmus', title: 'MUN Prep Session', cat: 'debating', type: 'workshop', d: 7, at: '16:00', dur: 2,
    venue: ['Seminar Hall 1', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'Position papers, caucusing and resolution drafting, taught by delegates from last year’s conferences.',
    desc: 'A working session: you will draft a position paper for a sample country and practise a moderated caucus. Bring a pen; there is no laptop requirement.',
    tags: ['MUN', 'Diplomacy'], pop: 36,
    details: { speaker: speaker('LITMUS MUN team'), topics: ['Position papers', 'Caucusing', 'Resolution drafting'], duration_minutes: 120, prerequisites: [], bring_own_laptop: false } },
  { id: 'e26', club: 'c-cse', title: 'Linear Algebra for ML: Revision Session', cat: 'academic', type: 'seminar', d: 3, at: '16:00', dur: 2,
    venue: ['Seminar Hall 1', 'AB3'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Eigenvectors and SVD, and where they show up in machine learning. Open to all years; no registration.',
    desc: 'Teaching assistants will revise the core ideas with worked examples, then connect them to PCA and recommendation systems.',
    tags: ['Mathematics', 'Machine Learning', 'Revision'], pop: 44,
    details: { speaker: speaker('Teaching assistants', 'School of Computer Science'), topic: 'Eigenvectors, SVD and where they show up in ML', q_and_a_enabled: true } },
  { id: 'e27', club: 'c-photo', title: 'Lightroom Editing Basics', cat: 'workshop', type: 'workshop', d: 9, at: '15:00', dur: 2,
    venue: ['Design Studio', 'AB1'], fee: ['fixed', 100], team: ['individual'], reg: ['google_forms', { before: 48 }],
    one: 'Exposure, white balance and colour grading on ten of your own photos. Bring a laptop with Lightroom installed.',
    desc: 'Bring ten photos you want to improve. We will edit one together, then you edit the rest with help from members. The fee covers a trial licence for the session.',
    tags: ['Photography', 'Editing'], pop: 25,
    details: { speaker: speaker('Photography Club editors'), topics: ['Exposure and white balance', 'Colour grading', 'Exporting for print and web'], duration_minutes: 120, prerequisites: ['Bring 10 photos to edit'], bring_own_laptop: true } },
  { id: 'e28', club: 'c-aws', title: 'Hack the Cloud CTF', cat: 'technical', type: 'competition', d: 20, at: '10:00', dur: 6,
    venue: ['Computer Lab 2', 'AB2'], fee: ['free'], team: ['range', 1, 3], reg: ['unstop', { before: 72 }],
    one: 'A capture-the-flag with web, crypto and cloud challenges. Solo or teams of up to three.',
    desc: 'Challenges are released at 10:00 AM and scored live. Ties are broken by the time of the last correct submission. No prior CTF experience is needed for the first tier.',
    tags: ['CTF', 'Cybersecurity', 'Cloud'], pop: 47,
    details: { prizes: [prize('Top three', 'AWS swag and certificates')], eligibility: 'Open to all branches', rounds: [{ name: 'Jeopardy', description: 'Web, crypto and cloud challenges' }], judging_criteria: ['Points, ties broken by time'] } },
  { id: 'e29', club: 'c-cse', title: 'Alumni Panel: Careers in AI', cat: 'career', type: 'seminar', d: 18, at: '15:00', dur: 2,
    venue: ['Main Auditorium', 'Main Block'], fee: ['free'], team: ['not_applicable'], reg: ['google_forms', { before: 48 }],
    one: 'Four alumni working in machine-learning roles on how they got there and what they would do differently.',
    desc: 'A moderated panel followed by open questions. Panelists work in applied ML, research and data engineering.',
    tags: ['Careers', 'AI', 'Alumni'], pop: 56,
    details: { speaker: speaker('Four alumni panelists', 'Roles in ML engineering and research'), topic: 'Breaking into AI work after a CS degree', q_and_a_enabled: true } },
  { id: 'e30', club: 'c-sports', title: 'Inter-Hostel Badminton Doubles', cat: 'sports', type: 'sports_match', d: 5, at: '16:00', dur: 4,
    venue: ['Indoor Games Hall', 'Sports Complex'], fee: ['free'], team: ['fixed', 2, 2], reg: ['google_forms', { before: 24 }],
    one: 'Knockout doubles between hostels, best of three games. Bring your own racket.',
    desc: 'Each hostel can enter up to two pairs. Shuttles are provided. Draws are posted at the venue an hour before the first match.',
    tags: ['Badminton', 'Doubles'], pop: 34,
    details: { sport: 'Badminton', match_type: 'Knockout', format: 'Doubles, best of three', teams: [] } },
  { id: 'e31', club: 'c-acm', title: 'Open Source Contribution Sprint', cat: 'technical', type: 'hackathon', d: 21, at: '10:00', dur: 6,
    venue: ['Computer Lab 1', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 72 }],
    one: 'Six hours to make your first pull request to a real project, with maintainers’ good-first-issues lined up.',
    desc: 'Mentors will have shortlisted beginner-friendly issues in documentation and tooling projects. Bring a laptop with Git set up.',
    tags: ['Open source', 'Git'], pop: 33,
    details: { themes: ['Documentation', 'Good first issues'], tracks: [], duration_hours: 6, prizes: [] } },
  { id: 'e32', club: 'c-tmc', title: 'Stand-up Comedy Evening', cat: 'cultural', type: 'cultural_show', d: 15, at: '19:00', dur: 2,
    venue: ['Auditorium Annex', 'Main Block'], fee: ['not_specified'], team: ['not_applicable'], reg: null,
    one: 'A guest comedian and three student openers. Doors open at 6:30 PM.',
    desc: 'An evening of stand-up with a short interval. Content will be kept campus-appropriate. Seating is first come, first served.',
    tags: ['Comedy', 'Stand-up'], pop: 61,
    details: { performances: [{ title: 'Headliner', performer: 'Guest comedian, to be announced' }], artists: [], auditions_required: false } },
  { id: 'e33', club: 'c-acm', title: 'Python for Beginners', cat: 'technical', type: 'workshop', d: -4, at: '16:00', dur: 2,
    venue: ['AB3 Seminar Hall', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'Variables, loops and functions in two hours, with exercises you can keep.',
    desc: 'An introduction for first-years with no programming background.', tags: ['Python', 'Beginners'], pop: 40,
    details: { speaker: speaker('ACM volunteers'), topics: ['Variables', 'Loops', 'Functions'], duration_minutes: 120, prerequisites: [], bring_own_laptop: true } },
  { id: 'e34', club: 'c-photo', title: 'Photography Exhibition', cat: 'cultural', type: 'social', d: -2, at: '10:00', dur: 8,
    venue: ['Library Gallery', 'Library Block'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Forty prints from club members, on display all day.', desc: 'A one-day exhibition of student work.', tags: ['Photography', 'Exhibition'], pop: 30,
    details: { extra: { notes: '' } } },
  { id: 'e35', club: 'c-ecell', title: 'Club Fair', cat: 'social', type: 'social', d: -9, at: '11:00', dur: 5,
    venue: ['Central Lawn', 'Campus'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Stalls from every club, with sign-ups on the spot.', desc: 'Meet the clubs and sign up for the ones you like.', tags: ['Clubs', 'Freshers'], pop: 44,
    details: { extra: { notes: '' } } },
  { id: 'e36', club: 'c-ieee', title: 'Hardware Hack Day', cat: 'hackathon', type: 'hackathon', d: 6, at: '09:00', dur: 8,
    venue: ['Electronics Lab', 'AB1'], fee: ['free'], team: ['range', 2, 3], reg: ['google_forms', { before: 48 }],
    one: 'A one-day build with sensors and microcontrollers.', desc: 'Teams of two or three build and demo a sensor project in a day.',
    tags: ['Hardware', 'IoT'], pop: 38, status: 'cancelled', cancel: 'The lab is booked for an exam that week. A new date will be announced.',
    details: { themes: ['Sensors'], tracks: [], duration_hours: 8, prizes: [] } },
  { id: 'e37', club: 'c-sports', title: 'Kabaddi Friendlies', cat: 'sports', type: 'sports_match', d: 8, at: '17:00', dur: 3,
    venue: ['Sports Complex Court', 'Sports Complex'], fee: ['free'], team: ['range', 7, 10], reg: ['google_forms', { before: 24 }],
    one: 'Friendly matches between hostel squads.', desc: 'Short friendly matches between hostel squads.', tags: ['Kabaddi'], pop: 20,
    status: 'cancelled', cancel: 'Ground maintenance. Matches will move to the next fixture window.',
    details: { sport: 'Kabaddi', match_type: 'Friendly', format: '7-a-side', teams: [] } },
  { id: 'e38', club: 'c-acm', title: 'Generative AI Workshop', cat: 'technical', type: 'workshop', d: 6, at: '16:00', dur: 2,
    venue: ['AB3 Seminar Hall', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 24 }],
    one: 'Prompting, retrieval and small fine-tunes: build a working assistant for a document set in two hours.',
    desc: 'Build a small question-answering assistant over a set of PDFs using retrieval, then compare it with a prompt-only version. Laptops required.',
    tags: ['AI', 'GenAI', 'Workshop'], pop: 0, status: 'pending_review', by: 'u-rohan',
    details: { speaker: speaker('ACM mentors'), topics: ['Prompting', 'Retrieval', 'Evaluating answers'], duration_minutes: 120, prerequisites: ['Basic Python'], bring_own_laptop: true } },
  { id: 'e39', club: 'c-ieee', title: 'IEEE Tech Symposium', cat: 'technical', type: 'seminar', d: 25, at: '10:00', dur: 8,
    venue: ['Main Auditorium', 'Main Block'], fee: ['free'], team: ['not_applicable'], reg: ['google_forms', { before: 72 }],
    one: 'A full day of talks on electronics, embedded systems and AI hardware.', desc: 'Talks and posters from students and invited speakers.',
    tags: ['Symposium', 'Electronics'], pop: 0, status: 'pending_review', by: 'u-ieee-admin',
    details: { speaker: speaker('Invited speakers'), topic: 'Electronics, embedded systems and AI hardware', q_and_a_enabled: true } },
  { id: 'e40', club: 'c-aura', title: 'Short Film Screening', cat: 'cultural', type: 'cultural_show', d: 19, at: '18:00', dur: 2.5,
    venue: ['Seminar Hall 2', 'AB2'], fee: ['free'], team: ['not_applicable'], reg: null,
    one: 'Six student short films followed by a discussion with the makers.', desc: 'Screening and discussion.',
    tags: ['Film', 'Screening'], pop: 0, status: 'pending_review', by: 'u-aura-admin',
    details: { performances: [], artists: [], auditions_required: false } },
  { id: 'e41', club: 'c-acm', title: 'Competitive Programming Contest', cat: 'technical', type: 'competition', d: 17, at: '14:00', dur: 3,
    venue: ['Computer Lab 1', 'AB3'], fee: ['free'], team: ['individual'], reg: ['google_forms', { before: 48 }],
    one: 'Five problems, three hours, ranked by solved count and penalty time.', desc: 'A rated contest on an online judge. Details to follow.',
    tags: ['Competitive programming', 'Algorithms'], pop: 0, status: 'draft', by: 'u-rohan',
    details: { prizes: [], eligibility: '', rounds: [], judging_criteria: [] } },
  { id: 'e42', club: 'c-acm', title: 'Alumni Meet', cat: 'career', type: 'social', d: 22, at: '17:00', dur: 2,
    venue: ['To be confirmed', ''], fee: ['not_specified'], team: ['not_applicable'], reg: null,
    one: 'An evening with ACM alumni and current members.', desc: 'Informal meet with alumni.', tags: ['Alumni'], pop: 0,
    status: 'rejected', reject: 'Venue booking confirmation is missing. Add the approved venue and submit again.', by: 'u-rohan',
    details: { extra: { notes: '' } } },
  { id: 'e43', club: 'c-robotics', title: 'Open Lab Day', cat: 'technical', type: 'social', d: 1, at: '17:00', dur: 2.5,
    venue: ['Robotics Lab', 'AB2'], fee: ['free'], team: ['not_applicable'], reg: ['google_forms', { before: 6 }],
    one: 'Drop in to see the club’s robots, try the arm controller and meet the team. Come any time in the window.',
    desc: 'The lab opens to everyone for an afternoon. Members will demo the line follower, the robotic arm and the drone rig.',
    tags: ['Robotics', 'Demo'], pop: 57,
    details: { extra: { notes: 'Drop in any time between 5:00 and 7:30 PM.' } } },
  { id: 'e44', club: 'c-acm', title: 'Data Structures Doubt Clearing', cat: 'academic', type: 'workshop', d: 0, at: '00:00', dur: 2, fromNowMin: 120,
    venue: ['Computer Lab 1', 'AB3'], fee: ['free'], team: ['individual'], reg: null,
    one: 'Bring your questions on trees, graphs and dynamic programming. Senior students answer on the whiteboard.',
    desc: 'An informal doubt-clearing session before the mid-semester exam. Bring specific questions or problems you got stuck on.',
    tags: ['Data structures', 'Exams'], pop: 46,
    details: { speaker: speaker('ACM senior students'), topics: ['Trees', 'Graphs', 'Dynamic programming'], duration_minutes: 120, prerequisites: [], bring_own_laptop: false } },
];

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export function buildSeed(now: Date): Seed {
  const rand = mulberry32(42);
  const today = startOfDayIST(now);

  const clubs: Club[] = [
    ...CLUBS.map(([id, name, s, category, description]) => ({ id, name, slug: s, description, category, verified: true, admin_ids: [] as string[] })),
    ...PENDING_CLUBS.map(([id, name, s, category, description, requested_by]) => ({ id, name, slug: s, description, category, verified: false, admin_ids: [] as string[], requested_by })),
  ];
  const clubById = new Map(clubs.map((c) => [c.id, c]));

  const mkUser = (id: string, name: string, email: string, role: Role, extra: Partial<User> = {}): StoredUser => ({
    id, name, email, role, password: 'demo1234', interests: [], preferred_categories: [], followed_club_ids: [], managed_club_ids: [], ...extra,
  });
  const users: StoredUser[] = [
    mkUser('u-ananya', 'Ananya Verma', 'student@muj-demo.edu', 'student', { interests: ['AI', 'Machine Learning', 'Hackathons'], preferred_categories: ['technical', 'hackathon'], followed_club_ids: ['c-acm', 'c-ieee'] }),
    mkUser('u-rohan', 'Rohan Kapoor', 'acm@muj-demo.edu', 'club_admin', { interests: ['Open source', 'AI'], managed_club_ids: ['c-acm'] }),
    mkUser('u-admin', 'Platform Admin', 'admin@muj-demo.edu', 'platform_admin'),
    mkUser('u-ieee-admin', 'Tanvi Singh', 'ieee@muj-demo.edu', 'club_admin', { managed_club_ids: ['c-ieee'] }),
    mkUser('u-aura-admin', 'Kabir Malhotra', 'aura@muj-demo.edu', 'club_admin', { managed_club_ids: ['c-aura'] }),
    mkUser('u-ishita', 'Ishita Bansal', 'ishita@muj-demo.edu', 'student'),
    mkUser('u-karthik', 'Karthik Nair', 'karthik@muj-demo.edu', 'student'),
    mkUser('u-sana', 'Sana Qureshi', 'sana@muj-demo.edu', 'student'),
    mkUser('u-dev', 'Dev Choudhary', 'dev@muj-demo.edu', 'student'),
    mkUser('u-meghna', 'Meghna Joshi', 'meghna@muj-demo.edu', 'student'),
    mkUser('u-yash', 'Yash Agarwal', 'yash@muj-demo.edu', 'student'),
    mkUser('u-pooja', 'Pooja Rathore', 'pooja@muj-demo.edu', 'student'),
  ];
  for (const u of users) for (const cid of u.managed_club_ids) clubById.get(cid)?.admin_ids.push(u.id);

  const parseAt = (at: string) => at.split(':').map(Number) as [number, number];

  const events: MockEvent[] = DEFS.map((def) => {
    let start: Date;
    if (def.fromNowMin != null) {
      start = new Date(Math.ceil((now.getTime() + def.fromNowMin * MS.MIN) / (15 * MS.MIN)) * 15 * MS.MIN);
    } else {
      const [h, m] = parseAt(def.at);
      const day = addDaysIST(today, def.d);
      const w = istWall(day);
      start = istDate(w.y, w.m, w.d, h, m);
    }
    const end = new Date(start.getTime() + def.dur * MS.HOUR);

    let deadline: string | null = null;
    if (def.reg && def.reg[1]) {
      const r = def.reg[1];
      deadline = ('before' in r ? new Date(start.getTime() - r.before * MS.HOUR) : new Date(now.getTime() + r.fromNow * MS.HOUR)).toISOString();
    }
    const club = clubById.get(def.club)!;
    const fee = { type: def.fee[0], amount: def.fee[1] ?? null, currency: 'INR' as const };
    const team = { type: def.team[0], min: def.team[1] ?? null, max: def.team[2] ?? null };
    const registration = { required: def.reg !== null, platform: def.reg ? def.reg[0] : null, deadline, url: def.reg ? `https://forms.example/${slug(def.title)}` : null };
    const status = def.status ?? 'published';

    const pop = def.pop;
    const jitter = () => 0.7 + rand() * 0.6;
    const win = status === 'published'
      ? { saves: Math.round(pop * 0.5 * jitter()), views: Math.round(pop * 6 * jitter()), registration_clicks: Math.round(pop * 1.6 * jitter()) }
      : { saves: 0, views: 0, registration_clicks: 0 };
    const details = JSON.parse(JSON.stringify(def.details)) as DetailsBag;
    if (def.id === 'e03') details.audition_date = dayKeyIST(today);

    return {
      id: def.id,
      club_id: def.club,
      created_by: def.by ?? (def.club === 'c-acm' ? 'u-rohan' : `u-${def.club.slice(2)}-admin`),
      title: def.title,
      one_liner: def.one,
      description: def.desc,
      club: { id: club.id, name: club.name, slug: club.slug },
      category: def.cat,
      event_type: def.type,
      tags: def.tags,
      poster_url: null,
      schedule: { start: start.toISOString(), end: end.toISOString() },
      venue: { name: def.venue[0], building: def.venue[1] || null, room: null },
      fee: { ...fee, display: feeDisplay(fee) },
      team: { ...team, display: teamDisplay(team) },
      registration,
      registration_open: registrationOpen(registration, start.toISOString(), now),
      featured: def.featured != null,
      featured_at: def.featured != null ? new Date(now.getTime() - def.featured * MS.HOUR).toISOString() : null,
      status,
      stats: { saves: Math.round(win.saves * (2.2 + rand())), views: Math.round(win.views * (2.4 + rand())) },
      details,
      contact: { name: `${club.name} desk`, email: `${club.slug}@muj-demo.edu` },
      rejection_reason: def.reject ?? null,
      cancel_reason: def.cancel ?? null,
      published_at: status === 'published' ? new Date(start.getTime() - 14 * MS.DAY).toISOString() : null,
      win,
    };
  });

  const hoursAgo = (h: number) => new Date(now.getTime() - h * MS.HOUR).toISOString();
  const posts: StoredPost[] = [];
  const comments: StoredComment[] = [];
  const author = (id: string) => ({ id, name: users.find((u) => u.id === id)!.name });
  let cn = 0;
  const addPost = (id: string, type: PostScopeType, ref: string | null, by: string, title: string, body: string, h: number, like: number, insightful: number, pinned = false) => {
    const ref_label = type === 'event' ? events.find((e) => e.id === ref)?.title ?? null : type === 'club' ? clubById.get(ref!)?.name ?? null : null;
    posts.push({ id, scope: { type, ref_id: ref, ref_label }, author: author(by), title, body, created_at: hoursAgo(h), comment_count: 0, reaction_counts: { like, insightful }, pinned, status: 'active' });
  };
  const addComment = (postId: string, by: string, body: string, h: number, parent: string | null = null, like = 0) => {
    const id = `cm${++cn}`;
    comments.push({ id, post_id: postId, parent_id: parent, author: author(by), body, created_at: hoursAgo(h), reaction_counts: { like, insightful: 0 }, my_reaction: null, status: 'active' });
    posts.find((p) => p.id === postId)!.comment_count++;
    return id;
  };

  addPost('p1', 'event', 'e01', 'u-ishita', 'Looking for two teammates for the GenAI Hackathon',
    'I have a backend developer (FastAPI) and a designer. We need someone comfortable with retrieval or fine-tuning. Reply with something you have built, even a small project.', 5, 9, 2);
  const c1 = addComment('p1', 'u-karthik', 'I built a retrieval chatbot over course PDFs last semester. Happy to join if you still have a slot.', 4, null, 3);
  addComment('p1', 'u-ishita', 'Great. Can you share the repository link here?', 3.5, c1);
  addComment('p1', 'u-karthik', 'Posting it tonight. It runs on a laptop without a GPU, which might matter for the venue.', 3, c1, 1);
  addComment('p1', 'u-dev', 'If you are still short, I can help with the demo and slides.', 1.5);

  addPost('p2', 'global', null, 'u-yash', 'Tomorrow’s AI/ML workshop and Open Lab Day overlap by an hour',
    'The workshop is 4 to 6 PM in AB3 and Open Lab Day starts at 5 PM in AB2. Is anyone planning to do both? I would like to know if the lab visit works after 6.', 8, 6, 4);
  const c2 = addComment('p2', 'u-rohan', 'Open Lab Day is drop-in, so you can arrive after 6 and still see everything. The robotic arm demo repeats at 6:30.', 6.5, null, 5);
  addComment('p2', 'u-yash', 'That works, thanks. I will go to the workshop first.', 6, c2);

  addPost('p3', 'event', 'e03', 'u-meghna', 'Do sound checks count inside the 15-minute set?',
    'The registration page says 15-minute sets. Does our sound check come out of that, or is it separate?', 10, 4, 1);
  addComment('p3', 'u-sana', 'Separate. Last year sound checks were at 5:30 PM and the sets started on time at 7.', 9, null, 2);

  addPost('p4', 'global', null, 'u-dev', 'How I prepared for the AWS Cloud Practitioner exam in three weeks',
    'I used the official exam guide, two sets of practice questions and one weekend on the free tier. Most of the exam is vocabulary: know what each service is for and how it is billed. The study jam on Saturday is a good way to find the gaps.', 30, 18, 11);
  const c4 = addComment('p4', 'u-pooja', 'Which practice questions did you use? I only found one free set.', 28);
  addComment('p4', 'u-dev', 'The ones linked in the exam guide, plus the club’s shared sheet. I will ask the club to pin it.', 27, c4, 2);
  addComment('p4', 'u-sana', 'The billing section surprised me. Reserved vs spot pricing came up twice.', 20, null, 1);

  addPost('p5', 'club', 'c-litmus', 'u-pooja', 'First time debating: what should I read before the Open House?',
    'I have never done parliamentary format. Is there anything worth reading beforehand, or is the briefing enough?', 14, 5, 2);
  addComment('p5', 'u-sana', 'The briefing covers the format. If you want a head start, skim a one-page British Parliamentary primer and read two or three news stories you could argue either side of.', 12, null, 4);

  addPost('p6', 'global', null, 'u-karthik', 'Please put the building number on every poster',
    'Half the posters I see say “Seminar Hall” with no block. Newcomers lose ten minutes finding it.', 52, 14, 3);
  addComment('p6', 'u-admin', 'Every event on HappenMUJ lists the building and room. If a club’s poster leaves it out, tell the club admin and we will remind them.', 50, null, 6);

  addPost('p7', 'event', 'e04', 'u-yash', 'Squad lists: do we need names on registration?',
    'Our department has two possible squads. Do we submit the names when we register, or at the briefing?', 20, 2, 0);

  addPost('p8', 'club', 'c-acm', 'u-rohan', 'Which projects should the open-source sprint target?',
    'We are shortlisting beginner-friendly repositories for the sprint. Suggest projects you already use and would like to contribute to.', 36, 7, 5);
  addComment('p8', 'u-karthik', 'Anything with a good CONTRIBUTING file. I would vote for a documentation tool; the first pull request is easier there.', 34, null, 3);
  addComment('p8', 'u-ananya', 'Seconding docs. A static site generator would also work.', 33);

  const saved: Seed['saved'] = {
    'u-ananya': [
      { event_id: 'e02', status: 'saved', saved_at: hoursAgo(20) },
      { event_id: 'e43', status: 'saved', saved_at: hoursAgo(18) },
      { event_id: 'e01', status: 'registration_initiated', saved_at: hoursAgo(40) },
      { event_id: 'e12', status: 'saved', saved_at: hoursAgo(10) },
      { event_id: 'e33', status: 'saved', saved_at: hoursAgo(120) },
    ],
  };

  return { clubs, users, events, posts, comments, saved, reactions: {}, ranking: structuredClone(DEFAULT_RANKING) };
}
