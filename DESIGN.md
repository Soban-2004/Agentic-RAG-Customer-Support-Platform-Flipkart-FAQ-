---
name: Aster
description: A clearer kind of support, expressed through aubergine, lilac, and apricot.
colors:
  bg: "#100e1b"
  surface: "#191625"
  muted-surface: "#282335"
  sidebar-bg: "#14111e"
  border: "#342e43"
  hover: "#272134"
  brand: "#b8a2ff"
  brand-hover: "#cbbaff"
  brand-soft: "#302644"
  brand-ring: "#b8a2ff42"
  ink: "#f4f0fb"
  muted: "#b5abc7"
  accent: "#f5ae8f"
  success: "#92d8bd"
  danger: "#ff9baf"
  danger-soft: "#3e1f2e"
  button-ink: "#211731"
  scene-lilac: "#9e75ff24"
  scene-apricot: "#ed9f7520"
  light-bg: "#f3f0f8"
  light-surface: "#fcfaff"
  light-muted-surface: "#e9e2f3"
  light-sidebar-bg: "#ece6f4"
  light-border: "#d5cbdf"
  light-hover: "#e8e0f2"
  light-brand: "#6741b8"
  light-brand-hover: "#543096"
  light-brand-soft: "#e6ddf5"
  light-brand-ring: "#6741b833"
  light-ink: "#281e39"
  light-muted: "#6e5e80"
  light-accent: "#a84e2f"
  light-success: "#267457"
  light-danger: "#b12d50"
  light-danger-soft: "#f9e1e8"
  light-button-ink: "#fff"
  light-scene-lilac: "#9e75ff16"
  light-scene-apricot: "#ed9f7516"
typography:
  display:
    fontFamily: "Outfit, sans-serif"
    fontSize: "clamp(42px,4.7vw,64px)"
    fontWeight: 500
    lineHeight: 1.05
    letterSpacing: "-.035em"
  headline:
    fontFamily: "Outfit, sans-serif"
    fontSize: "clamp(44px,5vw,72px)"
    fontWeight: 500
    lineHeight: 1.08
    letterSpacing: "-.035em"
  title:
    fontFamily: "Outfit, sans-serif"
    fontSize: "30px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-.025em"
  body:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "15px"
  answer:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "14px"
    lineHeight: 1.8
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 550
  code:
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
rounded:
  action: "8px"
  compact: "6px"
  chip: "7px"
  send: "9px"
  new-conversation: "10px"
  starter: "12px"
  composer: "14px"
  auth-panel: "16px"
  shell: "18px"
spacing:
  starter-gap: "10px"
  message-gap: "24px"
  shell-inset: "14px"
  auth-form: "40px"
components:
  button-primary:
    backgroundColor: "{colors.brand}"
    textColor: "{colors.button-ink}"
    rounded: "{rounded.action}"
    padding: "13px 16px"
  button-primary-hover:
    backgroundColor: "{colors.brand-hover}"
  button-secondary:
    textColor: "{colors.ink}"
    rounded: "{rounded.action}"
    padding: "12px 16px"
  button-new-conversation:
    backgroundColor: "{colors.brand-soft}"
    textColor: "{colors.brand}"
    rounded: "{rounded.new-conversation}"
    padding: "12px 15px"
  starter-action:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.starter}"
    padding: "17px 18px"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.action}"
    padding: "12px 14px"
  composer:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.composer}"
    padding: "13px 12px 13px 19px"
  composer-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.chip}"
    padding: "6px 10px"
  auth-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.auth-panel}"
    width: "100%"
  assistant-message:
    backgroundColor: "{colors.surface}"
    rounded: "2px 14px 14px"
    padding: "17px 20px"
  user-message:
    backgroundColor: "{colors.brand-soft}"
    rounded: "14px 2px 14px 14px"
    padding: "17px 20px"
---

# Design System: Aster

## Overview

**Creative North Star: "The Aster Aperture"**

Aster gives customer support an independent, cinematic identity. A small star sits within delicate orbital rings, with lilac and apricot light diffusing across aubergine surfaces. The user approved color, typography, effects, and animation as the foremost expression of this identity. The imagery is generated directly in SVG and CSS; no image compositions are part of the shipped system.

Large Outfit headings create an expressive first impression. DM Sans carries the practical work of questions, answers, history, and forms. Atmospheric welcome screens resolve into legible, bounded conversation surfaces. The signature stays consistent across entry, saved chat, and anonymous demo experiences.

**Key Characteristics:**

- Aubergine foundations, lilac actions, and apricot punctuation.
- Orbital SVG geometry with a star-shaped core.
- Broad, soft scene light with restrained surface borders.
- Pointer-lit starter actions and slow ambient motion.
- Light, dark, and system modes with reduced-motion support.

## Colors

The default palette is dusky aubergine with luminous lilac and warm apricot; light mode replaces the foundation with lavender paper and deepens the same accents.

### Primary

- **Lilac:** `brand` marks primary actions, links, focus, selection, and the brand symbol. `brand-hover` brightens an enabled primary action. `brand-soft` supports selected history and user messages; `brand-ring` provides translucent pointer light and field focus.
- **Deep Lilac:** the corresponding `light-brand` family keeps the primary role legible against light surfaces.

### Secondary

- **Apricot:** `accent` punctuates the wordmark, orbit, selected starter icons, and connecting state. Its light counterpart is a darker warm clay. It complements lilac without becoming a second primary-button treatment.

### Tertiary

- **Mint:** `success` indicates ready connections.
- **Rose:** `danger` and `danger-soft` identify failures and destructive hover states.

### Neutral

- **Aubergine:** `bg`, `sidebar-bg`, `surface`, and `muted-surface` distinguish scene, navigation, contained content, and code or disabled surfaces.
- **Lavender Ink:** `ink` and `muted` separate reading text from explanatory copy and metadata. `border` and `hover` provide quiet structure and interaction states.
- **Lavender Paper:** all `light-*` values are the exact overrides for the equivalent dark roles, including button text and translucent scene light.

**The Theme Roles Rule.** Use runtime CSS variables for colors. Explicit light and dark selections override the OS; system mode follows `prefers-color-scheme`. Dark is the initial fallback, and the chosen mode is stored under `theme`.

## Typography

**Display Font:** Outfit, sans-serif fallback.

**Body Font:** DM Sans, sans-serif fallback.

**Code Font:** ui-monospace, monospace fallback.

Rounded geometric display letters and tightly tracked headings carry the identity. Body text stays quieter and uses normal sentence casing.

### Hierarchy

- **Display:** the welcome heading uses the frontmatter display role. Its final mobile size is (44px), and its large-screen size is (68px).
- **Headline:** the entry story uses the headline role; mobile uses (36px).
- **Title:** form headings use the title role; mobile uses (26px).
- **Body:** the global baseline is the body role. Welcome descriptions use (1.7) line height; authentication story copy uses (16px, 1.8).
- **Answer:** markdown uses the answer role; mobile answer text is (13px). User text uses (14px, 1.7).
- **Label:** form labels use the label role. Starter titles use (13px, 550), or (12px) on mobile. Supporting copy uses (10–13px), depending on role.
- **Wordmark:** Outfit (31px, 600, 1, -.035em); compact (27px), and compact mobile (24px).

## Layout

The desktop app occupies (100dvh), with the frontmatter shell inset and a bordered, clipped shell. Navigation is a fixed-width column (260px). The conversation is centered at a maximum width of (820px); its default gap is the message-gap token. The composer has a maximum width of (876px), including horizontal padding (28px). Starter actions form two columns at a maximum width of (610px).

Authentication uses a centered (1160px) grid with columns (1.15fr 1fr), gap (80px), and a form panel capped at (450px). The page padding is (32px 5.5vw 22px).

Responsive rules, including later overrides in the stylesheet:

- At widths at least (1500px), the welcome heading becomes (68px) and starter grid grows to (660px).
- At widths at most (1050px), authentication gap becomes (35px), form padding (30px), and chat header padding (16px 22px). The header theme selector is hidden; the sidebar selector remains available.
- At widths at most (767px), the shell loses its outer inset, border, and radius. Navigation becomes a fixed drawer with a blurred backdrop. Chat header uses (14px 18px) padding and a minimum height of (66px). Conversation gap becomes (20px), starter actions stack in one column capped at (440px), and the final welcome orbit becomes (155px × 95px). The composer uses (10px 16px max(15px,env(safe-area-inset-bottom))) padding, and the textarea grows to (16px) type. Authentication stacks vertically with gap (28px), form padding (28px), and a centered story.
- At desktop heights at most (760px), the welcome orbit is (160px × 105px), heading (48px), and starter padding (13px 16px). Authentication reduces its orbit to (200px × 135px) and form padding to (30px).
- At mobile heights at most (740px), starter padding reduces to (10px 12px). Later mobile overrides still win for the welcome orbit (155px × 95px), heading (44px), and description bottom margin (21px).
- Coarse pointers enlarge message actions to (40px × 40px) and theme buttons to (34px × 34px).

## Elevation & Depth

Depth comes primarily from tonal surfaces, fine borders, and two radial scene gradients. The orbit haze uses a (12px) blur, and the core has a soft colored drop shadow. Starter actions reveal a (150px) radial pool at the pointer and lift by (-2px); primary actions lift by (-1px). The mobile drawer uses a lateral shadow and a backdrop with (4px) blur.

### Shadow Vocabulary

- **Small:** `--shadow-sm` is defined as `0 4px 12px #05030e25` in dark mode and `0 4px 12px #44305b08` in light mode. It is an available token, not a claimed shadow on every surface.
- **Medium:** `--shadow-md` is defined as `0 20px 60px #05030e50` in dark mode and `0 20px 60px #44305b12` in light mode.
- **Composer focus:** `0 5px 22px var(--scene-lilac)` accompanies the brand-colored border.
- **Field focus:** `0 0 0 3px var(--brand-ring)` surrounds authentication fields.
- **Drawer:** `15px 0 60px #0005` separates mobile navigation from the scene.

**The Atmospheric Depth Rule.** Keep ordinary panels grounded in their surface and border roles; reserve visible glow for the orbital signature, pointer response, and focus.

## Shapes

Rounded rectangles organize actions, fields, and surfaces. The frontmatter records actual radii rather than a synthesized scale. Small icon controls use the compact and send radii; larger starter, composer, authentication, and shell boundaries become progressively softer. Message corners distinguish authors: the assistant has a small leading upper corner, while the user has a small trailing upper corner. The scroll-to-latest control and status dots are circles.

The brand mark is an inward-curving four-point star with a central cutout. Three elliptical SVG rings intersect around it; thin strokes (.8), low opacity (.32 or .2), and an apricot satellite keep the silhouette airy.

## Components

### Buttons

Primary actions use lilac fill, button ink, and the frontmatter primary-button dimensions. Hover shifts to brand-hover and lifts the button; disabled authentication submit buttons reduce opacity (.7). Secondary links use a bordered rounded outline with a hover surface. New-conversation buttons use brand-soft at rest and switch to solid brand on hover. The global keyboard focus outline is (2px) brand with (4px) offset.

### Chips

Composer suggestions are small bordered surface buttons with muted text. Hover changes their text and border to brand. Their dimensions are in the frontmatter; these suggestions are actions, not selected filters.

### Cards / Containers

Starter cards pair a lilac or apricot icon with a title, supporting line, and directional arrow. Pointer coordinates drive the radial highlight; hover also changes the border to brand. The auth panel is a bordered surface with the auth-panel radius. Message containers use surface or brand-soft according to the author, and support markdown tables and code blocks with local horizontal scrolling.

### Inputs / Fields

Authentication fields sit on the scene background with a quiet border and visible labels. Focus replaces the border with brand and adds the brand-ring shadow. Password visibility controls sit inside the field edge. Form errors use danger-soft with danger text.

The composer groups a transparent textarea and square send control inside a bordered surface. Focus-within changes its border and glow. The textarea grows to six lines, with the final CSS cap (144px); longer content scrolls. Send is disabled for empty input or unavailable interactions and uses muted-surface with muted text. Enter sends, Shift + Enter inserts a line break, and composition input is respected.

### Navigation

The sidebar contains the compact wordmark, new-conversation action, history, theme control, and account actions. Active history uses brand-soft with brand text; hover uses hover. Destructive actions reveal danger with danger-soft. Light/dark/system buttons use a bordered segmented container and brand-soft for the pressed state. Mobile navigation becomes a drawer over a blurred scrim.

### Orbital signature and motion

The welcome orbit is normally (210px × 145px), with a core (54px × 54px); authentication uses (270px × 180px). Rings make one turn over (45s), while the core breathes between scale (1) and (1.08) over (7s). Welcome content arrives over (.8s), resolving blur (5px) and vertical offset (8px). Sidebar entry uses (.3s), starting at horizontal offset (-18px) and opacity (.8). Thinking dots pulse over (1.4s), staggered by (.15s); streaming cursors use (1s).

The CSS UI easing is `cubic-bezier(.16,1,.3,1)`. React chat transitions use the separate `EASE_UI` tuple `[0,0,0.2,1]` from `frontend/src/lib/motion.ts`. Surface color transitions use (.3s), border and text transitions (.25s); starter movement uses (.25s). The welcome and orbital effects are CSS animations, with the orbit and brand drawn in SVG.

**The Reduced Motion Rule.** Under `prefers-reduced-motion: reduce`, disable animations and transitions and use automatic scrolling. The welcome remains sharp and stationary; the identity remains visible without motion.

## Do's and Don'ts

### Do:

- **Do** use runtime theme variables so surfaces, text, status, and glow adapt together.
- **Do** keep Outfit on expressive headings and DM Sans on practical reading and controls.
- **Do** reuse the star, elliptical orbit, lilac light, and apricot punctuation across entry and chat.
- **Do** preserve visible keyboard focus and reduced-motion behavior.
- **Do** retain the implemented width and height adaptations, including the final cascade overrides.

### Don't:

- **Don't** hard-code dark-only colors into shared components.
- **Don't** replace the shipped code-led orbital signature with an unrelated image treatment.
- **Don't** apply welcome-scale ambient motion to message reading surfaces.
- **Don't** make connection readiness, errors, or example data rely on decorative color alone.
