"""
Broader rules for a run's data type (LIBRARYTYPE), for runs the ORFik
vocabulary leaves blank.

ORFik's matcher only answers when exactly one term matches, so titles such as
'RIBOseq Ba/F3 Rpl22' or 'RF 293T4A DOX-3 [ribo_DOX_3]' get nothing. The rules
here are ordered instead: specific assays first (ribosome-bound tRNA,
mitoribosome, RiboTag, polysome fractions), then RNA-seq markers, then generic
Ribo-seq terms. Only the run's own text is used first; the study's text is
used only when the run says nothing, and only when the study describes a
single kind of library.
"""
import re

# Attributes that describe the library itself; checked with the title and
# library name.
ASSAY_ATTRIBUTES = re.compile(
    r'^(fraction|library.*|assay.*|.*seq.*|molecule.*|sample.?type|ip|'
    r'experimental factor: (fraction|protocol|rna type|library.*))$',
    re.IGNORECASE)
# Attributes that often describe the starting material for every library in
# the study (GEO 'source': 'Liver Total RNA'); used only if the above say
# nothing.
CONTEXT_ATTRIBUTES = re.compile(
    r'^(source_name|tag|treatment|antibody|description)$', re.IGNORECASE)


# GEO experiment titles end with the organism and the SRA library strategy:
# 'GSM123: Ribo_WT_rep1; Mus musculus; RNA-Seq'. That strategy is often
# RNA-Seq even for Ribo-seq libraries, so only the sample part is evidence.
GEO_EXPERIMENT_TITLE = re.compile(
    r'^(?:GSM\d+:\s*)?(.*?);\s*[^;]+;\s*[^;]+$')


def clean_experiment_title(title: str) -> str:
    match = GEO_EXPERIMENT_TITLE.match(title or '')
    return match.group(1) if match else (title or '')


def normalise(text: str) -> str:
    """Lower-case, and make _ . / [ ] etc. word boundaries."""
    text = re.sub(r'([a-z])([A-Z][a-z])', r'\1 \2', text or '')  # MitoRibo
    return ' ' + re.sub(r'[\W_]+', ' ', text.lower()) + ' '


def rx(pattern):
    return re.compile(pattern)


# (label, pattern) in priority order. Patterns run on normalise()d text.
RUN_RULES = [
    ('Ribo-tRNA-Seq', rx(r' ribo t ?rna | ribosome bound t ?rna ')),
    ('tRNA-Seq', rx(r' t ?rna seq | trna (capture|sequencing|profil)')),
    ('Mito-Ribo-Seq', rx(r' mito ?ribo| mito ?ip ribo | mitoribosom| mt ribo ')),
    ('Disome-Seq', rx(r' di ?some')),
    ('RMS', rx(r' rms | ribosome methylation ')),
    ('RiboTag', rx(r' ribo ?tag | trap seq | trap | translating ribosome '
                   r'affinity| ski trip ')),
    ('Polysome-Seq', rx(r' (heavy|light) poly ?some| poly ?som(e|al) (rna|'
                        r'fraction)| associated with \d+ \d+ ribo'
                        r'| associated with \d+ ribo| poly ?ribosom')),
    # 'input' is the RNA control, even in 'input rep2 (Ribo-seq)'. In
    # selective/proximity profiling it means total footprints, but those
    # studies are handled before these rules.
    ('RNA-Seq', rx(r' input ')),
    # Footprint wording is specific enough to beat 'mRNA' in e.g.
    # 'ribosome-protected mRNA fragments'.
    ('Ribo-Seq', rx(r' footprint| rpfs? | ribosome protected| ribo ?seq'
                    r'| riboseq | ribosome bound m?rna '
                    r'| (1\d|2\d|3\d) (2\d|3\d|4\d) ?nt | ribo\d')),
    # 'input mRNA for Ribosome Profiling' is the RNA-seq control, so RNA
    # markers beat generic ribosome wording.
    ('RNA-Seq', rx(r' (m|total |poly ?a )?rna ?seq| input | total rna '
                   r'| poly ?a (rna|selected)| transcriptome | ribo ?depleted'
                   r'| ribo ?zero | ribominus | tot ?rna | mrna ')),
    ('Ribo-Seq', rx(r' ribo | ribosome profil| ribo profil| rfp | 80 ?s '
                    r'| monosom| ribo lite ')),
]

# Words that make "IP"/"total"/"translatome" runs readable from the study.
STUDY_RULES = [
    ('RiboTag', rx(r' ribo ?tag | trap | translating ribosome affinity')),
    ('Polysome-Seq', rx(r' polysome (profil|seq|fraction)')),
    # In selective and proximity-specific ribosome profiling, 'total' and
    # 'input' are the total footprints, and IP/pulldown the selected ones.
    ('Selective Ribo-Seq', rx(r' selective ribosome profil| serp | '
                              r'co ?translational (assembly|folding|'
                              r'interaction)| proximity specific ribosome'
                              r'| bir ?a ')),
    ('Ribo-Seq', rx(r' ribo ?seq| ribosome profil| footprint| riboseq ')),
    ('RNA-Seq', rx(r' rna ?seq| transcriptom| mrna seq')),
]
NOT_RNA_STRATEGIES = {'mnase-seq', 'chip-seq', 'atac-seq', 'wgs', 'wxs',
                      'bisulfite-seq', 'dnase-hypersensitivity'}


def run_label(texts):
    """Label from the run's own texts, or ''."""
    return explain(texts)[0]


def explain(texts):
    """(label, evidence) where evidence quotes what matched, for review."""
    text = normalise(' '.join(t for t in texts if t))
    for label, pattern in RUN_RULES:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 40)
            return label, f'...{text[start:match.end() + 40].strip()}...'
    return '', ''


def study_labels(text):
    text = normalise(text)
    return [label for label, pattern in STUDY_RULES if pattern.search(text)]


def classify(run_texts, study_text, strategy='', source='',
             context_texts=()):
    """
    Returns (label, rule) where rule says how it was decided:
      'run'    the run's own title/library name/attributes
      'study'  the study describes only one kind of library
      'serp'   selective ribosome profiling study: IP vs total
      'not rna' DNA/chromatin library (candidate for removal)
    """
    if source.upper() == 'GENOMIC' and strategy.lower() in NOT_RNA_STRATEGIES:
        return 'Not RNA', 'not rna'
    labels = study_labels(study_text)
    text = normalise(' '.join(t for t in run_texts if t))
    if 'Selective Ribo-Seq' in labels:
        if re.search(r' ip | pull ?down | ap | biotin ', text) and \
                not re.search(r' input | total ', text):
            return 'Selective Ribo-Seq', 'serp'
        if re.search(r' total | input ', text):
            return 'Ribo-Seq', 'serp'
    label = run_label(run_texts) or run_label(context_texts)
    if label == 'Ribo-Seq' and ' translatome ' in text and \
            'RiboTag' in labels:
        return 'RiboTag', 'run'
    if label:
        return label, 'run'
    if ' translatome ' in text or re.search(r' ip ', text):
        for candidate in ('RiboTag', 'Polysome-Seq'):
            if candidate in labels:
                return candidate, 'study'
        # e.g. Ribo-lite: 'paired transcriptome (RNA-seq) and translatome
        # (Ribo-seq)'
        if ' translatome ' in text and 'Ribo-Seq' in labels:
            return 'Ribo-Seq', 'study'
    families = [l for l in labels if l != 'Selective Ribo-Seq']
    if len(families) == 1:
        return families[0], 'study'
    return '', ''
