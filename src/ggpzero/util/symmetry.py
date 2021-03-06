from ggplib.util.symbols import SymbolFactory, ListTerm, Term


def reflect_vertical(x, y, x_cords, y_cords):
    x_idx = x_cords.index(x)
    return x_cords[len(x_cords) - x_idx - 1], y


def reflect_horizontal(x, y, x_cords, y_cords):
    y_idx = y_cords.index(y)
    return x, y_cords[len(y_cords) - y_idx - 1]


def rotate_90(x, y, x_cords, y_cords):
    ' anti-clockwise '
    assert len(x_cords) == len(y_cords)
    x_idx = x_cords.index(x)
    y_idx = y_cords.index(y)

    return x_cords[y_idx], y_cords[len(x_cords) - x_idx - 1]


symbol_factory = None


def symbolize(txt, pos):
    global symbol_factory
    if symbol_factory is None:
        symbol_factory = SymbolFactory()

    symbols = symbol_factory.symbolize(txt)
    symbols = symbols[pos]

    # convert terms to lists - make things simpler knowing it is a list of size 1+
    if isinstance(symbols, Term):
        return ListTerm((symbols,))

    return symbols


class Translator(object):
    def __init__(self, game_info, x_cords, y_cords):
        self.game_info = game_info
        self.x_cords = x_cords
        self.y_cords = y_cords

        self.base_symbols = [symbolize(b, 1) for b in self.game_info.model.bases]

        # the indexes into base for x/y
        self.base_root_term_indexes = {}

        # map base root term -> dict
        #      * maps from non-root terms -> index into model.bases
        self.base_root_term_to_mapping = {}

        # store all the action lists to lookup (similar to base_root_term_to_mapping)
        self.action_list = []
        for ri in range(len(self.game_info.model.roles)):
            self.action_list.append([symbolize(a, 2) for a in self.game_info.model.actions[ri]])

        # the indexes into actio for x/y
        self.action_root_term_indexes = {}

        # these are simply skipped from translating
        self.skip_base_root_terms = set()
        self.skip_action_root_term = set()

        # caches - only to speed things up a bit
        self.translate_basestate_cache = {}
        self.translate_action_cache = {}

        # set first time in translate_basestate_faster
        self.base_translate_symbols_indices = None

    def add_basetype(self, root_term, x_terms_idx, y_terms_idx):
        assert root_term not in self.base_root_term_indexes

        if not isinstance(x_terms_idx, list):
            x_terms_idx = [x_terms_idx]

        if not isinstance(y_terms_idx, list):
            y_terms_idx = [y_terms_idx]

        # create a dict for this root_term.  the dict will a be a mapping from x, y -> position on model
        self.base_root_term_indexes[root_term] = x_terms_idx, y_terms_idx

        mapping = self.base_root_term_to_mapping[root_term] = {}

        for model_bases_indx, terms in enumerate(self.base_symbols):
            if terms[0] != root_term:
                continue

            mapping[terms[1:]] = model_bases_indx

    def add_action_type(self, root_term, x_terms_idx, y_terms_idx):
        assert root_term not in self.action_root_term_indexes

        if not isinstance(x_terms_idx, list):
            x_terms_idx = [x_terms_idx]

        if not isinstance(y_terms_idx, list):
            y_terms_idx = [y_terms_idx]

        self.action_root_term_indexes[root_term] = x_terms_idx, y_terms_idx

    def add_skip_base(self, root_term):
        self.skip_base_root_terms.add(root_term)

    def add_skip_action(self, root_term):
        self.skip_action_root_term.add(root_term)

    def translate_terms(self, terms, x_terms_idx, y_terms_idx, do_reflection, rot_count):
        assert len(x_terms_idx) == len(y_terms_idx)
        new_terms = list(terms)
        for x_term_idx, y_term_idx in zip(x_terms_idx, y_terms_idx):
            x, y = terms[x_term_idx], terms[y_term_idx]

            if do_reflection:
                x, y = reflect_vertical(x, y, self.x_cords, self.y_cords)

            for _ in range(rot_count):
                x, y = rotate_90(x, y, self.x_cords, self.y_cords)

            new_terms[x_term_idx] = Term(x)
            new_terms[y_term_idx] = Term(y)

        return ListTerm(new_terms)

    def translate_basestate_helper(self, terms, do_reflection, rot_count):
        key = tuple(terms), do_reflection, rot_count
        try:
            return self.translate_basestate_cache[key]

        except KeyError:
            pass

        x_term_idx, y_term_idx = self.base_root_term_indexes[terms[0]]
        new_terms = self.translate_terms(terms, x_term_idx, y_term_idx, do_reflection, rot_count)

        # set value on new basestate
        base_term, extra_terms = new_terms[0], new_terms[1:]
        new_bs_indx = self.base_root_term_to_mapping[base_term][extra_terms]
        self.translate_basestate_cache[key] = new_bs_indx
        return new_bs_indx

    def translate_basestate_faster(self, basestate, do_reflection, rot_count):
        # all skips copied... phew
        new_basestate = list(basestate)

        if not do_reflection and rot_count == 0:
            return new_basestate

        if self.base_translate_symbols_indices is None:
            self.base_translate_symbols_indices = []
            for indx, terms in enumerate(self.base_symbols):
                if terms[0] in self.skip_base_root_terms:
                    continue

                if terms[0] not in self.base_root_term_indexes:
                    raise Exception("Not supported base %s" % str(terms))

                self.base_translate_symbols_indices.append(indx)

        set_these = []
        for indx in self.base_translate_symbols_indices:
            if new_basestate[indx]:
                terms = self.base_symbols[indx]
                new_bs_indx = self.translate_basestate_helper(terms, do_reflection, rot_count)
                set_these.append(new_bs_indx)
                new_basestate[indx] = 0

        for indx in set_these:
            new_basestate[indx] = 1

        return new_basestate

    def translate_basestate(self, basestate, do_reflection, rot_count):
        # takes tuple/list, return new list (including self)
        assert isinstance(basestate, (tuple, list))
        assert len(basestate) == len(self.base_symbols)

        new_basestate = [0 for _ in range(len(basestate))]

        for indx, terms in enumerate(self.base_symbols):
            if not basestate[indx]:
                continue

            if terms[0] in self.skip_base_root_terms:
                new_basestate[indx] = 1
                continue

            if terms[0] not in self.base_root_term_indexes:
                raise Exception("Not supported base %s" % str(terms))

            new_bs_indx = self.translate_basestate_helper(terms, do_reflection, rot_count)
            new_basestate[new_bs_indx] = 1

        return new_basestate

    def translate_action(self, role_index, legal, do_reflection, rot_count):
        key = role_index, legal, do_reflection, rot_count
        try:
            return self.translate_action_cache[key]

        except KeyError:
            pass

        terms = self.action_list[role_index][legal]

        root_term = terms[0]
        if root_term in self.skip_action_root_term:
            self.translate_action_cache[key] = legal
            return legal

        # convert the action
        x_terms_idx, y_terms_idx = self.action_root_term_indexes[terms[0]]
        new_terms = self.translate_terms(terms, x_terms_idx, y_terms_idx, do_reflection, rot_count)

        for legal_idx, other in enumerate(self.action_list[role_index]):
            if new_terms == other:
                self.translate_action_cache[key] = legal_idx
                return legal_idx

        assert False, "Did not find translation"


class Prescription(object):
    def __init__(self, game_symmetries_desc):
        self.prescription = []

        # can't have both
        assert not (game_symmetries_desc.do_rotations_90 and
                    game_symmetries_desc.do_rotations_180)

        # define a prescription of what rotation/reflections to do
        if (game_symmetries_desc.do_rotations_90 or
            game_symmetries_desc.do_rotations_180):
            rotations = (0, 2) if game_symmetries_desc.do_rotations_180 else (0, 1, 2, 3)
            self.prescription += [(False, r) for r in rotations]

            if game_symmetries_desc.do_reflection:
                self.prescription += [(True, r) for r in rotations]

        elif game_symmetries_desc.do_reflection:
            self.prescription += [(False, 0), (True, 0)]

        else:
            # nothing
            self.prescription += [(False, 0)]

    def __iter__(self):
        for reflect, rotate in self.prescription:
            yield reflect, rotate


def create_translator(game_info, game_desc, game_symmetries):
    # create the translator
    t = translator = Translator(game_info, game_desc.x_cords, game_desc.y_cords)

    for ab in game_symmetries.apply_bases:
        t.add_basetype(ab.base_term, ab.x_terms_idx, ab.y_terms_idx)

    for ac in game_symmetries.apply_actions:
        t.add_action_type(ac.base_term, ac.x_terms_idx, ac.y_terms_idx)

    for term in game_symmetries.skip_bases:
        t.add_skip_base(term)

    for term in game_symmetries.skip_actions:
        t.add_skip_action(term)

    return translator
